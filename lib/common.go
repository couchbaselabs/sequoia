package sequoia

func chkerr(err error) {
	if err != nil {
		panic(err)
	}
}
