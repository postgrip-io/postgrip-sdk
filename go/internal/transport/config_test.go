package transport

import (
	"net/url"
	"testing"
)

func TestSameOriginNormalizesDefaultPorts(t *testing.T) {
	t.Parallel()
	for _, tc := range []struct {
		left  string
		right string
		want  bool
	}{
		{"https://api.example", "https://api.example:443/path", true},
		{"http://api.example", "http://api.example:80/path", true},
		{"https://api.example", "https://api.example:444/path", false},
		{"https://api.example", "http://api.example:443/path", false},
	} {
		left, err := url.Parse(tc.left)
		if err != nil {
			t.Fatal(err)
		}
		right, err := url.Parse(tc.right)
		if err != nil {
			t.Fatal(err)
		}
		if got := sameOrigin(left, right); got != tc.want {
			t.Fatalf("sameOrigin(%q, %q) = %v, want %v", tc.left, tc.right, got, tc.want)
		}
	}
}
