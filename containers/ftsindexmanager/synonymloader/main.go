package main

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"main/src-loader"
	"main/syn-loader"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
)

type ResponseObj struct {
	WordDocMap      map[string][]string `json:"word_doc_map"`
	FinalWordDocMap map[string][]string `json:"final_word_doc_map"`
}

type ScriptParams struct {
	Bucket      string `json:"bucket"`
	Scope       string `json:"scope"`
	Collection  string `json:"collection"`
	NumWorkers  int    `json:"workers"`
	CBURL       string `json:"host"`
	CBUser      string `json:"user"`
	CBPass      string `json:"pass"`
	NumDocs     int    `json:"numDocs"`
	Format      int    `json:"format"` // Only for SynLoader
}

type SynLoaderResponse struct {
	Success bool   `json:"success"`
	Message string `json:"message"`
}

func main() {
	r := chi.NewRouter()
	r.Use(middleware.Logger)

	r.Post("/run/src-loader", func(w http.ResponseWriter, r *http.Request) {
		executeScript(w, r)
	})

	r.Post("/run/syn-loader", func(w http.ResponseWriter, r *http.Request) {
		executeSynLoader(w, r)
	})

	fmt.Println("Server running on :5000")
	log.Fatal(http.ListenAndServe(":5000", r))
}

func executeScript(w http.ResponseWriter, r *http.Request) {
	body, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "Failed to read request body", http.StatusBadRequest)
		return
	}
	defer r.Body.Close()

	var params ScriptParams
	if err := json.Unmarshal(body, &params); err != nil {
		http.Error(w, "Invalid JSON format", http.StatusBadRequest)
		return
	}

	res, _ := srcloader.SrcLoader(params.Bucket, params.Scope, params.Collection, params.NumWorkers, params.CBURL, params.CBUser, params.CBPass, params.NumDocs)

	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusOK)
	json.NewEncoder(w).Encode(res)
}

func executeSynLoader(w http.ResponseWriter, r *http.Request) {
	body, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "Failed to read request body", http.StatusBadRequest)
		return
	}
	defer r.Body.Close()

	var params ScriptParams
	if err := json.Unmarshal(body, &params); err != nil {
		http.Error(w, "Invalid JSON format", http.StatusBadRequest)
		return
	}

	success, err := synloader.SynLoader(params.Bucket, params.Scope, params.Collection,params.Format, params.NumWorkers, params.CBURL, params.CBUser, params.CBPass)
	response := SynLoaderResponse{
		Success: success,
		Message: "SynLoader executed successfully",
	}

	if err != nil {
		response.Success = false
		response.Message = fmt.Sprintf("SynLoader execution failed: %v", err)
		w.WriteHeader(http.StatusInternalServerError)
	} else {
		w.WriteHeader(http.StatusOK)
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(response)
}
