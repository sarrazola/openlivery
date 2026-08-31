package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

// backendClient talks to the FastAPI internal WhatsApp router. Every call is
// authenticated with the shared bridge token.
type backendClient struct {
	baseURL string
	token   string
	client  *http.Client
}

func newBackendClient(baseURL, token string) *backendClient {
	return &backendClient{
		baseURL: baseURL,
		token:   token,
		client:  &http.Client{Timeout: 30 * time.Second},
	}
}

// call sends a request to /api/internal/whatsapp{path} and decodes the JSON
// response into out when out is not nil. Timeout zero uses the client default.
func (b *backendClient) call(ctx context.Context, method, path string, payload any, out any, timeout time.Duration) error {
	if timeout > 0 {
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(ctx, timeout)
		defer cancel()
	}
	var body io.Reader
	if payload != nil {
		data, err := json.Marshal(payload)
		if err != nil {
			return err
		}
		body = bytes.NewReader(data)
	}
	request, err := http.NewRequestWithContext(ctx, method, b.baseURL+"/api/internal/whatsapp"+path, body)
	if err != nil {
		return err
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Bridge-Token", b.token)
	response, err := b.client.Do(request)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	if response.StatusCode >= 400 {
		detail := fmt.Sprintf("FastAPI responded with %d", response.StatusCode)
		var parsed struct {
			Detail string `json:"detail"`
		}
		if err := json.NewDecoder(response.Body).Decode(&parsed); err == nil && parsed.Detail != "" {
			detail = parsed.Detail
		}
		return fmt.Errorf("%s", detail)
	}
	if out == nil || response.StatusCode == http.StatusNoContent {
		return nil
	}
	return json.NewDecoder(response.Body).Decode(out)
}

func (b *backendClient) setStatus(ctx context.Context, channelID, status string, extra map[string]any) error {
	payload := map[string]any{"status": status}
	for key, value := range extra {
		payload[key] = value
	}
	return b.call(ctx, http.MethodPut, "/channels/"+channelID+"/status", payload, nil, 0)
}
