package internal

import (
	"encoding/base64"
	"fmt"
	"github.com/go-faker/faker/v4"
	"math/rand"
)

// CompanyEmbeddingsNeeded returns how many embeddings are required per doc for docSchema=company.
// Requirement (per schema markers): embeddings only on employee objects, project objects, and location objects
// (NOT on company object and NOT on department object).
func CompanyEmbeddingsNeeded(departmentsCount, employeesPerDept, projectsPerDept, locationsCount int) (int, error) {
	if departmentsCount <= 0 {
		return 0, fmt.Errorf("departmentsCount must be > 0")
	}
	if employeesPerDept < 0 {
		return 0, fmt.Errorf("employeesPerDept must be >= 0")
	}
	if projectsPerDept < 0 {
		return 0, fmt.Errorf("projectsPerDept must be >= 0")
	}
	if locationsCount < 0 {
		return 0, fmt.Errorf("locationsCount must be >= 0")
	}
	return (departmentsCount * employeesPerDept) + (departmentsCount * projectsPerDept) + locationsCount, nil
}

func embeddingValue(vector []float32, base64Flag bool) any {
	if !base64Flag {
		return vector
	}
	byteSlice := FloatsToLittleEndianBytes(vector)
	return base64.StdEncoding.EncodeToString(byteSlice)
}

// BuildCompanyDoc builds the nested company document (as a map) and injects an embedding into:
// - each employee object
// - each project object
// - each location object
//
// Vector selection is driven by vectorIdxs, which should have length = CompanyEmbeddingsNeeded(...).
// This lets callers pre-shuffle vectors across documents so we don't reuse the same vectors predictably.
func BuildCompanyDoc(
	documentID string,
	vectors [][]float32,
	vectorIdxs []int,
	embeddingFieldName string,
	base64Flag bool,
	departmentsCount int,
	employeesPerDept int,
	projectsPerDept int,
	locationsCount int,
) (map[string]any, error) {
	if len(vectors) == 0 {
		return nil, fmt.Errorf("no vectors available to build company doc")
	}
	if embeddingFieldName == "" {
		return nil, fmt.Errorf("embeddingFieldName must be non-empty")
	}
	if employeesPerDept < 0 {
		return nil, fmt.Errorf("employeesPerDept must be >= 0")
	}
	needed, err := CompanyEmbeddingsNeeded(departmentsCount, employeesPerDept, projectsPerDept, locationsCount)
	if err != nil {
		return nil, err
	}
	if len(vectorIdxs) != needed {
		return nil, fmt.Errorf("vectorIdxs length mismatch: got %d, need %d", len(vectorIdxs), needed)
	}

	get := func(i int) []float32 {
		idx := vectorIdxs[i] % len(vectors)
		if idx < 0 {
			idx = -idx
		}
		return vectors[idx]
	}

	roles := []string{"Engineer", "Manager", "Salesperson", "Analyst", "Designer", "Support"}
	deptNames := []string{"Engineering", "Sales", "Marketing", "Finance", "HR", "Operations"}
	projectStatuses := []string{"ongoing", "completed", "blocked"}
	cities := []string{"Athens", "Berlin", "Dublin", "London", "Paris", "New York", "San Francisco"}
	countries := []string{"Greece", "USA", "Germany", "Ireland", "UK", "France"}

	companyName := faker.Word()
	if companyName == "" {
		companyName = "TechCorp"
	}

	// Embedding assignment order:
	// 0..(departmentsCount*employeesPerDept-1): employees
	// then departmentsCount*projectsPerDept embeddings for projects
	// then locationsCount embeddings for locations
	employeeEmbOffset := 0
	projectEmbOffset := departmentsCount * employeesPerDept
	locationEmbOffset := projectEmbOffset + (departmentsCount * projectsPerDept)

	departments := make([]any, 0, departmentsCount)
	employeeEmbIdx := 0
	projectEmbIdx := 0
	for d := 0; d < departmentsCount; d++ {
		deptName := deptNames[rand.Intn(len(deptNames))]
		// make name slightly varied so we don't repeat too much
		deptName = fmt.Sprintf("%s-%s", deptName, faker.Word())
		budget := 100000 + rand.Intn(5000000)

		employees := make([]any, 0, employeesPerDept)
		for e := 0; e < employeesPerDept; e++ {
			emb := embeddingValue(get(employeeEmbOffset+employeeEmbIdx), base64Flag)
			employeeEmbIdx++
			employees = append(employees, map[string]any{
				"name":             faker.Name(),
				"role":             roles[rand.Intn(len(roles))],
				embeddingFieldName: emb,
			})
		}

		projects := make([]any, 0, projectsPerDept)
		for p := 0; p < projectsPerDept; p++ {
			emb := embeddingValue(get(projectEmbOffset+projectEmbIdx), base64Flag)
			projectEmbIdx++
			projects = append(projects, map[string]any{
				"title":            fmt.Sprintf("Project-%s", faker.Word()),
				"status":           projectStatuses[rand.Intn(len(projectStatuses))],
				embeddingFieldName: emb,
			})
		}

		departments = append(departments, map[string]any{
			"name":      deptName,
			"budget":    budget,
			"employees": employees,
			"projects":  projects,
		})
	}

	locations := make([]any, 0, locationsCount)
	for i := 0; i < locationsCount; i++ {
		locations = append(locations, map[string]any{
			"city":             cities[rand.Intn(len(cities))],
			"country":          countries[rand.Intn(len(countries))],
			embeddingFieldName: embeddingValue(get(locationEmbOffset+i), base64Flag),
		})
	}

	doc := map[string]any{
		"company": map[string]any{
			"id":          fmt.Sprintf("c-%s", documentID),
			"name":        companyName,
			"departments": departments,
			"locations":   locations,
		},
	}

	return doc, nil
}
