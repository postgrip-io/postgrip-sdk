// Package transport owns configuration mechanics shared by public API planes.
package transport

import (
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"strings"
)

// ParseBaseURL validates a plane URL and preserves any reverse-proxy path.
func ParseBaseURL(plane, raw string, insecureDevelopment bool) (*url.URL, error) {
	raw = strings.TrimSpace(raw)
	baseURL, err := url.Parse(raw)
	if err != nil || baseURL.Host == "" || (baseURL.Scheme != "https" && !(insecureDevelopment && baseURL.Scheme == "http")) {
		return nil, fmt.Errorf("postgrip-%s: base URL must use HTTPS (or explicitly enable insecure development for HTTP)", plane)
	}
	if strings.ContainsAny(raw, "?#") || baseURL.RawQuery != "" || baseURL.Fragment != "" {
		return nil, fmt.Errorf("postgrip-%s: base URL must not contain a query or fragment", plane)
	}
	return baseURL, nil
}

// ManagementToken validates that the opaque common management token is set.
func ManagementToken(plane, raw string) (string, error) {
	token := strings.TrimSpace(raw)
	if token == "" {
		return "", fmt.Errorf("postgrip-%s: management token is required", plane)
	}
	return token, nil
}

// HTTPClient returns a copy that refuses cross-origin redirects so bearer
// credentials cannot be forwarded to another origin.
func HTTPClient(source *http.Client) *http.Client {
	if source == nil {
		source = http.DefaultClient
	}
	clientCopy := *source
	priorRedirect := clientCopy.CheckRedirect
	clientCopy.CheckRedirect = func(req *http.Request, via []*http.Request) error {
		if len(via) == 0 {
			return nil
		}
		origin := via[0].URL
		if !sameOrigin(req.URL, origin) {
			return http.ErrUseLastResponse
		}
		if priorRedirect != nil {
			return priorRedirect(req, via)
		}
		if len(via) >= 10 {
			return errors.New("stopped after 10 redirects")
		}
		return nil
	}
	return &clientCopy
}

func sameOrigin(left, right *url.URL) bool {
	return strings.EqualFold(left.Scheme, right.Scheme) &&
		strings.EqualFold(left.Hostname(), right.Hostname()) &&
		effectivePort(left) == effectivePort(right)
}

func effectivePort(value *url.URL) string {
	if port := value.Port(); port != "" {
		return port
	}
	switch strings.ToLower(value.Scheme) {
	case "http":
		return "80"
	case "https":
		return "443"
	default:
		return ""
	}
}

// FirstNonEmpty returns the first trimmed non-empty string.
func FirstNonEmpty(values ...string) string {
	for _, value := range values {
		if value = strings.TrimSpace(value); value != "" {
			return value
		}
	}
	return ""
}
