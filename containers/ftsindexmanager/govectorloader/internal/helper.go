package internal

import (
	"fmt"
	"math"
	"net"
	"os"
	"strings"
	"unsafe"
)

func FloatsToLittleEndianBytes(floats []float32) []byte {
	byteSlice := make([]byte, len(floats)*4)
	for i, num := range floats {
		bits := math.Float32bits(num)
		*(*uint32)(unsafe.Pointer(&byteSlice[i*4])) = bits
	}
	return byteSlice
}

func DatasetExists(filePath string) bool {
	_, err := os.Stat(filePath)
	return !os.IsNotExist(err)
}

func resolve(database string) []string {
	urls, err := lookupSRV(database)
	if err != nil {
		return nil
	}
	return urls
}

func lookupSRV(url string) ([]string, error) {
	url = strings.Replace(url, "couchbases://", "", -1)
	urls := []string{}
	var srvs []*net.SRV
	_, srvs, err := net.LookupSRV("couchbases", "tcp", url)
	if err != nil {
		return urls, err
	}
	if len(srvs) != 0 {
		for _, v := range srvs {
			//convert from net.SRV to a string
			url1 := v.Target
			url1 = url1[:len(url1)-1]
			urls = append(urls, url1)
		}
	} else {
		return urls, fmt.Errorf("failed to return host from SRV")
	}

	// Return URL with at least one element
	return urls, nil
}
