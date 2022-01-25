package main

import (
	"fmt"
	"net/http"
	"os"
)

func main() {
	port := os.Args[1]

	http.HandleFunc("/", HelloServer)
	fmt.Println(fmt.Sprintf("Starting at port %s", port))
	bind := fmt.Sprintf("%s:%s", "0.0.0.0", port)
	http.ListenAndServe(bind, nil)
}

func HelloServer(w http.ResponseWriter, r *http.Request) {
	fmt.Fprintf(w, "Hello, %s!\r\n", r.URL.Path[1:])
}
