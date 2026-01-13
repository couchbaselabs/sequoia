package internal

import (
	"archive/tar"
	"compress/gzip"
	"encoding/binary"
	"fmt"
	"io"
	"os"
	"os/exec"
)

func ReadDataset(datasetName string, datasetType string) ([][]float32, error) {
	var vecs = "source/" + datasetName + "/" + datasetName + "_" + datasetType + ".fvecs"
	vectors, err := ReadVectorsFromFile(vecs)
	if err != nil {
		fmt.Println("Error reading vectors from file:", err)
		return nil, err
	}
	return vectors, nil
}

func extractDataset(source string) {

	// Destination directory where the contents will be extracted
	destination := "source/"

	// Open the source file
	file, err := os.Open(source)
	if err != nil {
		fmt.Println("Error opening file:", err)
		return
	}
	defer file.Close()

	// Create a gzip reader
	gzipReader, err := gzip.NewReader(file)
	if err != nil {
		fmt.Println("Error creating gzip reader:", err)
		return
	}
	defer gzipReader.Close()

	// Create a tar reader
	tarReader := tar.NewReader(gzipReader)

	// Iterate through each file in the tar archive
	for {
		header, err := tarReader.Next()

		// If no more files in the archive, break the loop
		if err == io.EOF {
			break
		}

		if err != nil {
			fmt.Println("Error reading tar:", err)
			return
		}

		// Construct the full path for the file
		target := destination + header.Name

		// Create directory if it doesn't exist
		if header.Typeflag == tar.TypeDir {
			err = os.MkdirAll(target, os.FileMode(header.Mode))
			if err != nil {
				fmt.Println("Error creating directory:", err)
				return
			}
			continue
		}

		// Create the file
		file, err := os.Create(target)
		if err != nil {
			fmt.Println("Error creating file:", err)
			return
		}
		defer file.Close()

		// Copy file contents from tar to the newly created file
		_, err = io.Copy(file, tarReader)
		if err != nil {
			fmt.Println("Error extracting file:", err)
			return
		}
	}

	fmt.Println("Files extracted successfully!")
}

func DownloadDataset(url string, datasetName string) {
	saveName := datasetName + ".tar.gz"
	// Destination file path
	destination := "raw/" + saveName
	// Execute wget command
	cmd := exec.Command("wget", "-O", destination, url)
	output, err := cmd.CombinedOutput()
	if err != nil {
		fmt.Println("Error:", err)
		return
	}
	// Print wget command output
	fmt.Println(string(output))
	fmt.Println("File downloaded successfully!")
	extractDataset(destination)
}

func ReadVectorsFromFile(filepath string) ([][]float32, error) {

	// Open the file for reading
	file, err := os.Open(filepath)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	// Read the dimension of the vector type
	var dimension int32
	err = binary.Read(file, binary.LittleEndian, &dimension)
	if err != nil {
		return nil, err
	}
	fmt.Printf("Dimension is: %d\n", dimension)

	// Calculate the number of vectors in the dataset
	stat, err := file.Stat()
	if err != nil {
		return nil, err
	}
	fileSize := stat.Size()
	numVectors := fileSize / (4 + int64(dimension*4))
	fmt.Printf("Total number of vectors in dataset: %d\n", numVectors)

	// Reset file cursor to start
	_, err = file.Seek(0, 0)
	if err != nil {
		return nil, err
	}

	// Initialize the output vector slice
	outVector := make([][]float32, numVectors)

	// Read vectors from the file
	for i := 0; i < int(numVectors); i++ {
		// Skip the dimension bytes
		_, err := file.Seek(4, 1)
		if err != nil {
			return nil, err
		}

		// Read float values of size 4 bytes of length dimension
		vector := make([]float32, dimension)
		for j := 0; j < int(dimension); j++ {
			var value float32
			err := binary.Read(file, binary.LittleEndian, &value)
			if err != nil {
				return nil, err
			}
			vector[j] = value
		}

		outVector[i] = vector
	}

	return outVector, nil
}
