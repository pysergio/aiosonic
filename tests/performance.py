"""Performance test."""

import asyncio
import json
import os
import random
from argparse import ArgumentParser
from concurrent import futures
from datetime import datetime, timedelta
from multiprocessing import Process
from shutil import which
from time import sleep
from urllib.error import URLError
from urllib.request import urlopen

import aiohttp
import httpx
import requests
from uvicorn.main import Config, Server

import aiosonic
from aiosonic.connectors import TCPConnector
from aiosonic.pools import CyclicQueuePool

try:
    import uvloop

    uvloop.install()
except Exception:
    pass


async def app(scope, receive, send):
    assert scope["type"] == "http"
    res = b"foo"
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [
                [b"content-type", b"text/plain"],
                [b"content-length", b"%d" % len(res)],
            ],
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": res,
        }
    )


async def start_dummy_server(loop, port):
    """Start dummy server."""
    host = "0.0.0.0"

    config = Config(app, host=host, port=port, workers=2, log_level="warning")
    server = Server(config=config)

    await server.serve()


async def timeit_coro(func, *args, **kwargs):
    """To time stuffs."""
    repeat = kwargs.pop("repeat", 1000)
    before = datetime.now()
    # Concurrent coroutines
    await asyncio.gather(*[func(*args, **kwargs) for _ in range(repeat)])
    after = datetime.now()
    return (after - before) / timedelta(milliseconds=1)


async def performance_aiohttp(url, args):
    """Test aiohttp performance."""
    async with aiohttp.ClientSession(
        connector=aiohttp.TCPConnector(limit=args.concurrency)
    ) as session:
        return await timeit_coro(session.get, url, repeat=args.requests)


async def performance_aiosonic(url, args, pool_cls=None, timeouts=None):
    """Test aiohttp performance."""
    async with aiosonic.HTTPClient(
        TCPConnector(pool_size=args.concurrency, pool_cls=pool_cls)
    ) as client:
        return await timeit_coro(
            client.get, url, repeat=args.requests, timeouts=timeouts
        )


async def performance_httpx(url, args):
    """Test httpx performance."""
    async with httpx.AsyncClient(http2=False) as client:
        sem = asyncio.Semaphore(args.concurrency)

        async def httpx_coro(url):
            async with sem:
                res = await client.get(url)
                return await res.aread()

        return await timeit_coro(httpx_coro, url, repeat=args.requests)


def timeit_requests(url, args):
    """Timeit requests."""
    repeat = args.requests
    concurrency = args.concurrency
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(
        pool_connections=concurrency, pool_maxsize=concurrency
    )
    session.mount("http://", adapter)
    with futures.ThreadPoolExecutor(concurrency) as executor:
        to_wait = []
        before = datetime.now()
        for _ in range(repeat):
            to_wait.append(executor.submit(session.get, url))
        for fut in to_wait:
            fut.result()
        after = datetime.now()
    return (after - before) / timedelta(milliseconds=1)


def do_tests(url, args):
    """Start benchmark."""
    print("doing tests...")
    loop = asyncio.get_event_loop()

    # aiohttp
    res1 = loop.run_until_complete(performance_aiohttp(url, args))

    res2 = loop.run_until_complete(performance_aiosonic(url, args))

    # requests
    res3 = None
    if not args.skip_requests:
        res3 = timeit_requests(url, args)

    # aiosonic cyclic
    res4 = loop.run_until_complete(
        performance_aiosonic(url, args, pool_cls=CyclicQueuePool)
    )

    httpx_exc = False
    res5 = None
    if args.skip_httpx:
        httpx_exc = True
    else:
        try:
            res5 = loop.run_until_complete(performance_httpx(url, args))
        except Exception as exc:
            httpx_exc = exc
            print("httpx did break with: " + str(exc))

    to_print = {
        "aiosonic": "%d requests in %.2f ms" % (args.requests, res2),
        "aiosonic cyclic": "%d requests in %.2f ms" % (args.requests, res4),
        "aiohttp": "%d requests in %.2f ms" % (args.requests, res1),
    }

    if not args.skip_requests:
        to_print["requests"] = "%d requests in %.2f ms" % (args.requests, res3)

    if not httpx_exc:
        to_print["httpx"] = "%d requests in %.2f ms" % (args.requests, res5)

    print(json.dumps(to_print, indent=True))

    print("aiosonic is %.2f%% faster than aiohttp" % (((res1 / res2) - 1) * 100))

    if not args.skip_requests:
        print("aiosonic is %.2f%% faster than requests" % (((res3 / res2) - 1) * 100))

    print(
        "aiosonic is %.2f%% faster than aiosonic cyclic" % (((res4 / res2) - 1) * 100)
    )

    res = [
        ["aiohttp", res1],
        ["aiosonic", res2],
        ["aiosonic_cyclic", res4],
    ]

    if not args.skip_requests:
        res.append(["requests", res3])

    if not httpx_exc:
        print("aiosonic is %.2f%% faster than httpx" % (((res5 / res2) - 1) * 100))
        res.append(["httpx", res5])

    return res


def start_server(port):
    """Start server."""
    if which("go") is not None:
        os.system(f"./server {port}")
    else:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(start_dummy_server(loop, port))


def main():
    """Start."""
    parser = ArgumentParser()
    parser.add_argument("-n", "--requests", type=int, default=1000)
    parser.add_argument("-c", "--concurrency", type=int, default=25)
    parser.add_argument("--skip-requests", action="store_true")
    parser.add_argument("--skip-httpx", action="store_true")
    args = parser.parse_args()

    process = None

    port = random.randint(1000, 9000)
    url = "http://0.0.0.0:%d" % port
    if which("go") is not None:
        os.system("go build tests/server.go")

    process = Process(target=start_server, args=(port,))
    process.start()

    max_wait = datetime.now() + timedelta(seconds=5)
    while True:
        try:
            with urlopen(url) as response:
                response.read()
                break
        except URLError:
            sleep(1)
            if datetime.now() > max_wait:
                raise
    try:
        res = do_tests(url, args)
        assert "aiosonic" in sorted(res, key=lambda x: x[1])[0][0]
    finally:
        if process:
            process.terminate()


if __name__ == "__main__":
    main()
