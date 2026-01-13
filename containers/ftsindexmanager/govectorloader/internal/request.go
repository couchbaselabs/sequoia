package internal

import (
	"bytes"
	"crypto/tls"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io/ioutil"
	"net/http"
)

// APIClient struct to hold the base URL and the HTTP client
type APIClient struct {
	BaseURL string
	Client  *http.Client
}

// NewAPIClient creates a new APIClient with the given base URL
func NewAPIClient(baseURL string) *APIClient {
	return &APIClient{
		BaseURL: baseURL,
		Client: &http.Client{Transport: &http.Transport{
			TLSClientConfig: &tls.Config{InsecureSkipVerify: true},
		}},
	}
}

// DoRequest performs an HTTP request with the given method, endpoint, and payload
func (api *APIClient) DoRequest(method, username string, password string, payload interface{}) (*http.Response, error) {
	url := api.BaseURL

	var req *http.Request
	var err error

	if payload != nil {
		jsonData, err := json.Marshal(payload)
		//fmt.Println(string(jsonData))
		if err != nil {
			return nil, fmt.Errorf("error marshalling payload: %v", err)
		}
		req, err = http.NewRequest(method, url, bytes.NewBuffer(jsonData))
		req.Header.Set("Content-Type", "application/json")
	} else {
		req, err = http.NewRequest(method, url, nil)
	}
	if err != nil {
		return nil, fmt.Errorf("error creating %v request: %v", method, err)
	}
	auth := username + ":" + password
	encodedAuth := base64.StdEncoding.EncodeToString([]byte(auth))
	req.Header.Set("Authorization", "Basic "+encodedAuth)

	resp, err := api.Client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("error performing %v request: %v", method, err)
	}

	return resp, nil
}

// ProcessResponse reads and processes the response
func ProcessResponse(resp *http.Response) (map[string]interface{}, error) {
	body, err := ioutil.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("error reading response body: %v", err)
	}
	defer resp.Body.Close()

	var result map[string]interface{}
	if err := json.Unmarshal(body, &result); err != nil {
		return nil, fmt.Errorf("error unmarshalling response body: %v -- \nResponse= %v\n", err, string(body))
	}

	return result, nil
}
