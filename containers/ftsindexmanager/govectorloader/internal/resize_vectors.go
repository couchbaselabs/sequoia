package internal

import (
	"fmt"
	"math/rand"
	"strconv"
	"strings"
)

func DecriptResizeVariables(percentagesToResizeStr string, dimensionsForResizeStr string, percentagesToResize *[]float32, dimensionsForResize *[]int) {
	if percentagesToResizeStr != "" {
		var floatList []float32

		floatStrList := strings.Split(percentagesToResizeStr, ",")
		for _, floatStr := range floatStrList {
			floatVal, err := strconv.ParseFloat(floatStr, 32)
			if err != nil {
				fmt.Printf("Error parsing float value: %v\n", err)
				return
			}
			floatList = append(floatList, float32(floatVal))
		}
		*percentagesToResize = floatList

		var intList []int
		intStrList := strings.Split(dimensionsForResizeStr, ",")
		for _, intStr := range intStrList {
			intVal, err := strconv.Atoi(intStr)
			if err != nil {
				fmt.Printf("Error parsing integer value: %v\n", err)
				return
			}
			intList = append(intList, intVal)
		}

		*dimensionsForResize = intList

		fmt.Println(*dimensionsForResize)
		fmt.Println(*percentagesToResize)

	}
}

func ResizeVectors(trainVecs *[][]float32, percentages []float32, dims []int) error {
	totalVectors := len(*trainVecs)

	// Get random indices for vectors to resize
	indicesToResize := rand.Perm(totalVectors)

	if len(percentages) != len(dims) {
		return fmt.Errorf("percentages and dims lists must have the same length")
	}

	var totalPercentage float32
	for _, per := range percentages {
		totalPercentage += per
	}

	if totalPercentage > 1 {
		return fmt.Errorf("total percentage of docs to update should be less than 1")
	}

	for idx, percentage := range percentages {
		vectorsToResize := int(percentage * float32(totalVectors))

		currentIndices := indicesToResize[:vectorsToResize]
		indicesToResize = indicesToResize[vectorsToResize:]

		fmt.Printf("Number of docs resized with dimension %d is %d\n", dims[idx], len(currentIndices))

		for _, index := range currentIndices {
			vector := (*trainVecs)[index]
			currentDim := len(vector)

			if currentDim < dims[idx] {
				(*trainVecs)[index] = repeatValues(vector, dims[idx])
			} else if currentDim > dims[idx] {
				(*trainVecs)[index] = vector[:dims[idx]]
			}
		}
	}

	return nil
}

func repeatValues(vector []float32, targetDim int) []float32 {
	repeatedValues := make([]float32, 0, targetDim)
	for i := 0; i < (targetDim+len(vector)-1)/len(vector); i++ {
		repeatedValues = append(repeatedValues, vector...)
	}
	return repeatedValues[:targetDim]
}
