package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"regexp"
	"strings"
)

type RawEntry struct {
	Word     string   `json:"word"`
	Synonyms []string `json:"synonyms"`
}

type WordEntry struct {
	Word     []string `json:"word"`
	Synonyms []string `json:"synonyms"`
}

// Regular expression to allow only alphabets (uppercase/lowercase)
var validWordPattern = regexp.MustCompile(`^[a-zA-Z]+$`)

// Function to check if a word is valid
func isValidWord(word string) bool {
	return validWordPattern.MatchString(word)
}

func ProcessFile(inputFile, outputFile string) error {
	file, err := os.Open(inputFile)
	if err != nil {
		return fmt.Errorf("error opening input file: %w", err)
	}
	defer file.Close()

	wordMap := make(map[string]map[string]struct{})

	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		var raw RawEntry
		if err := json.Unmarshal(scanner.Bytes(), &raw); err != nil {
			fmt.Println("Skipping invalid JSON:", scanner.Text())
			continue
		}

		lowerWord := strings.ToLower(raw.Word)
		if !isValidWord(lowerWord) {
			continue // Skip invalid words
		}

		if _, exists := wordMap[lowerWord]; !exists {
			wordMap[lowerWord] = make(map[string]struct{})
		}

		for _, synonym := range raw.Synonyms {
			lowerSynonym := strings.ToLower(synonym)
			if lowerSynonym != lowerWord && isValidWord(lowerSynonym) {
				wordMap[lowerWord][lowerSynonym] = struct{}{}
			}
		}
	}

	if err := scanner.Err(); err != nil {
		return fmt.Errorf("error reading input file: %w", err)
	}

	var finalData []WordEntry
	for word, synonymSet := range wordMap {
		synonyms := make([]string, 0, len(synonymSet))
		for synonym := range synonymSet {
			synonyms = append(synonyms, synonym)
		}
		if len(synonyms) == 0 {
			continue
		}
		finalData = append(finalData, WordEntry{Word: []string{word}, Synonyms: synonyms})
	}

	output, err := os.Create(outputFile)
	if err != nil {
		return fmt.Errorf("error creating output file: %w", err)
	}
	defer output.Close()

	encoder := json.NewEncoder(output)
	encoder.SetIndent("", "  ")
	if err := encoder.Encode(finalData); err != nil {
		return fmt.Errorf("error writing output file: %w", err)
	}

	fmt.Println("Processing complete. Output saved to", outputFile)
	return nil
}

func main() {
	if len(os.Args) < 3 {
		fmt.Println("Usage: go run process.go <input.jsonl> <output.json>")
		return
	}

	inputFile := os.Args[1]
	outputFile := os.Args[2]

	if err := ProcessFile(inputFile, outputFile); err != nil {
		fmt.Println("Error:", err)
		os.Exit(1)
	}
}
