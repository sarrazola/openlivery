package main

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"
	"sync"
	"time"

	qrcode "github.com/skip2/go-qrcode"
	"google.golang.org/protobuf/proto"

	"go.mau.fi/whatsmeow"
	"go.mau.fi/whatsmeow/proto/waE2E"
	"go.mau.fi/whatsmeow/store"
	"go.mau.fi/whatsmeow/store/sqlstore"
	"go.mau.fi/whatsmeow/types"
	"go.mau.fi/whatsmeow/types/events"
	waLog "go.mau.fi/whatsmeow/util/log"
)

// Skip forwarding media larger than this; the backend also caps at 20 MB.
const maxMediaBytes = 18 * 1024 * 1024

// Flat placeholder waveform: iOS WhatsApp may not render a voice note without one.
var voiceWaveform = func() []byte {
	waveform := make([]byte, 64)
	for i := range waveform {
		waveform[i] = 24
	}
	return waveform
}()

type channelConfig struct {
	ID        string          `json:"id"`
	Enabled   bool            `json:"enabled"`
	AuthState json.RawMessage `json:"auth_state"`
}

// authMarker is what the bridge stores through PUT /channels/{id}/auth. The
// session keys themselves live in the whatsmeow store; the backend only needs
// to know which device belongs to the channel, and that a session exists.
type authMarker struct {
	Provider  string `json:"provider"`
	DeviceJID string `json:"device_jid"`
}

type inboundResult struct {
	Accepted          bool    `json:"accepted"`
	Reply             *string `json:"reply"`
	OutboundMessageID *string `json:"outbound_message_id"`
}

type outboundMedia struct {
	kind     string // image | audio | video | file
	data     []byte
	mime     string
	filename string
	seconds  uint32
}

type channelRuntime struct {
	channelID string
	client    *whatsmeow.Client

	mu            sync.Mutex
	stopRequested bool
}

func (r *channelRuntime) stopped() bool {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.stopRequested
}

func (r *channelRuntime) requestStop() {
	r.mu.Lock()
	r.stopRequested = true
	r.mu.Unlock()
}

type manager struct {
	api       *backendClient
	container *sqlstore.Container
	log       waLog.Logger

	mu       sync.Mutex
	runtimes map[string]*channelRuntime
}

func newManager(api *backendClient, container *sqlstore.Container, log waLog.Logger) *manager {
	return &manager{
		api:       api,
		container: container,
		log:       log,
		runtimes:  make(map[string]*channelRuntime),
	}
}

func (m *manager) runtime(channelID string) *channelRuntime {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.runtimes[channelID]
}

// connectChannel is idempotent: a channel that is already running is left
// alone. Fresh devices go through the QR pairing flow; known devices reconnect
// without user interaction.
func (m *manager) connectChannel(ctx context.Context, channelID string) error {
	m.mu.Lock()
	if current, ok := m.runtimes[channelID]; ok && !current.stopped() {
		m.mu.Unlock()
		return nil
	}
	m.mu.Unlock()

	var config channelConfig
	if err := m.api.call(ctx, http.MethodGet, "/channels/"+channelID, nil, &config, 0); err != nil {
		return err
	}
	if !config.Enabled {
		return errors.New("The channel is disabled")
	}

	device, hasSession := m.deviceForChannel(ctx, config)
	status := "connecting"
	if hasSession {
		status = "reconnecting"
	}
	if err := m.api.setStatus(ctx, channelID, status, nil); err != nil {
		return err
	}

	client := whatsmeow.NewClient(device, m.log.Sub(channelID))
	runtime := &channelRuntime{channelID: channelID, client: client}
	m.mu.Lock()
	m.runtimes[channelID] = runtime
	m.mu.Unlock()
	client.AddEventHandler(func(evt any) { m.handleEvent(runtime, evt) })

	if client.Store.ID == nil {
		qrChan, err := client.GetQRChannel(context.Background())
		if err != nil {
			m.dropRuntime(runtime)
			return err
		}
		if err := client.Connect(); err != nil {
			m.dropRuntime(runtime)
			return err
		}
		go m.pumpQR(runtime, qrChan)
		return nil
	}
	if err := client.Connect(); err != nil {
		m.dropRuntime(runtime)
		return err
	}
	return nil
}

// deviceForChannel maps the channel to its whatsmeow device using the marker
// stored on the backend. Anything else in auth_state (for example a session
// from the previous bridge) means a fresh pairing.
func (m *manager) deviceForChannel(ctx context.Context, config channelConfig) (device *store.Device, hasSession bool) {
	if len(config.AuthState) > 0 {
		var marker authMarker
		if err := json.Unmarshal(config.AuthState, &marker); err == nil && marker.DeviceJID != "" {
			if jid, err := types.ParseJID(marker.DeviceJID); err == nil {
				if found, err := m.container.GetDevice(ctx, jid); err == nil && found != nil {
					return found, true
				}
				m.log.Warnf("channel %s: stored device %s not found in the session store, pairing again", config.ID, marker.DeviceJID)
			}
		}
	}
	return m.container.NewDevice(), false
}

func (m *manager) pumpQR(runtime *channelRuntime, qrChan <-chan whatsmeow.QRChannelItem) {
	ctx := context.Background()
	for evt := range qrChan {
		if runtime.stopped() {
			return
		}
		switch evt.Event {
		case "code":
			png, err := qrcode.Encode(evt.Code, qrcode.Medium, 360)
			if err != nil {
				m.log.Errorf("channel %s: could not render the QR: %v", runtime.channelID, err)
				continue
			}
			dataURL := "data:image/png;base64," + base64.StdEncoding.EncodeToString(png)
			m.statusOrLog(ctx, runtime.channelID, "qr", map[string]any{"qr_code": dataURL})
		case "success":
			m.statusOrLog(ctx, runtime.channelID, "connecting", nil)
		case "timeout":
			// Nobody scanned: release the runtime and reset the channel so the
			// portal shows a clean disconnected state.
			m.dropRuntime(runtime)
			runtime.client.Disconnect()
			if err := m.api.call(ctx, http.MethodDelete, "/channels/"+runtime.channelID+"/auth", nil, nil, 0); err != nil {
				m.log.Errorf("channel %s: could not reset after QR timeout: %v", runtime.channelID, err)
			}
			return
		default:
			m.statusOrLog(ctx, runtime.channelID, "error", map[string]any{"error": truncate("Pairing failed: "+evt.Event, 500)})
		}
	}
}

func (m *manager) handleEvent(runtime *channelRuntime, rawEvt any) {
	ctx := context.Background()
	switch evt := rawEvt.(type) {
	case *events.Message:
		if runtime.stopped() {
			return
		}
		if err := m.processIncoming(ctx, runtime, evt); err != nil {
			detail := truncate("Could not process an incoming message: "+err.Error(), 500)
			m.log.Errorf("channel %s: %s", runtime.channelID, detail)
			m.statusOrLog(ctx, runtime.channelID, "error", map[string]any{"error": detail})
		}

	case *events.PairSuccess:
		m.persistMarker(ctx, runtime)

	case *events.Connected:
		m.persistMarker(ctx, runtime)
		extra := map[string]any{}
		if id := runtime.client.Store.ID; id != nil {
			extra["phone_number"] = id.User
		}
		if name := runtime.client.Store.PushName; name != "" {
			extra["display_name"] = name
		}
		m.statusOrLog(ctx, runtime.channelID, "connected", extra)

	case *events.Disconnected:
		if runtime.stopped() {
			return
		}
		// whatsmeow reconnects on its own; reflect the gap in the portal.
		m.statusOrLog(ctx, runtime.channelID, "reconnecting", map[string]any{"error": "Connection interrupted. Retrying..."})

	case *events.StreamReplaced:
		m.dropRuntime(runtime)
		m.statusOrLog(ctx, runtime.channelID, "error", map[string]any{"error": "Another process took over this WhatsApp session"})

	case *events.TemporaryBan:
		m.statusOrLog(ctx, runtime.channelID, "error", map[string]any{"error": truncate("WhatsApp temporarily banned this number: "+evt.String(), 500)})

	case *events.ClientOutdated:
		m.statusOrLog(ctx, runtime.channelID, "error", map[string]any{"error": "The bridge build is too old for WhatsApp. Update the whatsmeow dependency."})

	case *events.LoggedOut:
		// The phone unlinked the device: clear everything on both sides.
		if runtime.stopped() {
			return
		}
		m.dropRuntime(runtime)
		if err := m.api.call(ctx, http.MethodDelete, "/channels/"+runtime.channelID+"/auth", nil, nil, 0); err != nil {
			m.log.Errorf("channel %s: could not clear the session after logout: %v", runtime.channelID, err)
		}
	}
}

func (m *manager) persistMarker(ctx context.Context, runtime *channelRuntime) {
	id := runtime.client.Store.ID
	if id == nil {
		return
	}
	payload := map[string]any{"auth_state": authMarker{Provider: "whatsmeow", DeviceJID: id.String()}}
	if err := m.api.call(ctx, http.MethodPut, "/channels/"+runtime.channelID+"/auth", payload, nil, 0); err != nil {
		m.log.Errorf("channel %s: could not save the session marker: %v", runtime.channelID, err)
	}
}

// remoteJIDFor keeps conversation continuity: anonymous @lid chats are mapped
// back to the real phone JID whenever the store knows it, so the backend keys
// the conversation the same way it always has.
func (m *manager) remoteJIDFor(ctx context.Context, runtime *channelRuntime, chat types.JID) string {
	if chat.Server == types.HiddenUserServer {
		if pn, err := runtime.client.Store.LIDs.GetPNForLID(ctx, chat); err == nil && !pn.IsEmpty() {
			return pn.ToNonAD().String()
		}
	}
	return chat.ToNonAD().String()
}

func (m *manager) processIncoming(ctx context.Context, runtime *channelRuntime, evt *events.Message) error {
	if !isDirectIncoming(evt.Info) {
		return nil
	}
	text := incomingText(evt.Message)
	media := incomingMedia(evt.Message)
	if text == "" && media == nil {
		return nil
	}
	remoteJID := m.remoteJIDFor(ctx, runtime, evt.Info.Chat)

	body := map[string]any{
		"external_message_id": evt.Info.ID,
		"remote_jid":          remoteJID,
		"text":                text,
	}
	if evt.Info.PushName != "" {
		body["sender_name"] = evt.Info.PushName
	}
	if media != nil && media.length <= maxMediaBytes {
		data, err := runtime.client.Download(ctx, media.download)
		if err != nil {
			m.log.Errorf("channel %s: could not download media: %v", runtime.channelID, err)
		} else if len(data) <= maxMediaBytes {
			body["media_kind"] = media.kind
			body["media_mime"] = media.mimetype
			body["media_base64"] = base64.StdEncoding.EncodeToString(data)
		}
	}

	var result inboundResult
	// A synchronous AI reply (REPLY_DEBOUNCE_SECONDS=0) can take a while.
	if err := m.api.call(ctx, http.MethodPost, "/channels/"+runtime.channelID+"/inbound", body, &result, 120*time.Second); err != nil {
		return err
	}
	if result.Reply == nil || *result.Reply == "" {
		return nil
	}
	sentID, err := m.sendMessage(ctx, runtime.channelID, remoteJID, *result.Reply, nil)
	if err != nil {
		return err
	}
	if result.OutboundMessageID != nil {
		confirm := map[string]any{"message_id": *result.OutboundMessageID, "external_message_id": sentID}
		if err := m.api.call(ctx, http.MethodPost, "/channels/"+runtime.channelID+"/outbound-confirm", confirm, nil, 0); err != nil {
			m.log.Errorf("channel %s: could not confirm the outbound message: %v", runtime.channelID, err)
		}
	}
	return nil
}

func (m *manager) sendMessage(ctx context.Context, channelID, remoteJID, text string, media *outboundMedia) (string, error) {
	runtime := m.runtime(channelID)
	if runtime == nil || runtime.stopped() {
		return "", errors.New("WhatsApp is not connected")
	}
	jid, err := types.ParseJID(remoteJID)
	if err != nil {
		return "", fmt.Errorf("invalid destination: %w", err)
	}

	message := &waE2E.Message{Conversation: proto.String(text)}
	if media != nil {
		message, err = m.buildMediaMessage(ctx, runtime, text, media)
		if err != nil {
			return "", err
		}
	}
	sent, err := runtime.client.SendMessage(ctx, jid, message)
	if err != nil {
		return "", err
	}
	// Audio messages have no caption on WhatsApp; deliver it as a follow-up text.
	if media != nil && media.kind == "audio" && text != "" {
		if _, err := runtime.client.SendMessage(ctx, jid, &waE2E.Message{Conversation: proto.String(text)}); err != nil {
			m.log.Errorf("channel %s: could not send the audio caption: %v", channelID, err)
		}
	}
	return sent.ID, nil
}

func (m *manager) buildMediaMessage(ctx context.Context, runtime *channelRuntime, text string, media *outboundMedia) (*waE2E.Message, error) {
	mediaType := whatsmeow.MediaDocument
	switch media.kind {
	case "image":
		mediaType = whatsmeow.MediaImage
	case "video":
		mediaType = whatsmeow.MediaVideo
	case "audio":
		mediaType = whatsmeow.MediaAudio
	}
	uploaded, err := runtime.client.Upload(ctx, media.data, mediaType)
	if err != nil {
		return nil, fmt.Errorf("could not upload the media: %w", err)
	}
	length := proto.Uint64(uint64(len(media.data)))
	message := &waE2E.Message{}
	switch media.kind {
	case "image":
		message.ImageMessage = &waE2E.ImageMessage{
			Mimetype:      proto.String(media.mime),
			URL:           proto.String(uploaded.URL),
			DirectPath:    proto.String(uploaded.DirectPath),
			MediaKey:      uploaded.MediaKey,
			FileEncSHA256: uploaded.FileEncSHA256,
			FileSHA256:    uploaded.FileSHA256,
			FileLength:    length,
		}
		if text != "" {
			message.ImageMessage.Caption = proto.String(text)
		}
	case "video":
		message.VideoMessage = &waE2E.VideoMessage{
			Mimetype:      proto.String(media.mime),
			URL:           proto.String(uploaded.URL),
			DirectPath:    proto.String(uploaded.DirectPath),
			MediaKey:      uploaded.MediaKey,
			FileEncSHA256: uploaded.FileEncSHA256,
			FileSHA256:    uploaded.FileSHA256,
			FileLength:    length,
		}
		if text != "" {
			message.VideoMessage.Caption = proto.String(text)
		}
	case "audio":
		isVoice := strings.Contains(media.mime, "ogg")
		mimetype := media.mime
		if isVoice {
			// iOS requires this exact mimetype to play a voice note.
			mimetype = "audio/ogg; codecs=opus"
		}
		message.AudioMessage = &waE2E.AudioMessage{
			Mimetype:      proto.String(mimetype),
			URL:           proto.String(uploaded.URL),
			DirectPath:    proto.String(uploaded.DirectPath),
			MediaKey:      uploaded.MediaKey,
			FileEncSHA256: uploaded.FileEncSHA256,
			FileSHA256:    uploaded.FileSHA256,
			FileLength:    length,
		}
		if isVoice {
			message.AudioMessage.PTT = proto.Bool(true)
			message.AudioMessage.Waveform = voiceWaveform
		}
		if media.seconds > 0 {
			message.AudioMessage.Seconds = proto.Uint32(media.seconds)
		}
	default:
		filename := media.filename
		if filename == "" {
			filename = "file"
		}
		message.DocumentMessage = &waE2E.DocumentMessage{
			Title:         proto.String(filename),
			FileName:      proto.String(filename),
			Mimetype:      proto.String(media.mime),
			URL:           proto.String(uploaded.URL),
			DirectPath:    proto.String(uploaded.DirectPath),
			MediaKey:      uploaded.MediaKey,
			FileEncSHA256: uploaded.FileEncSHA256,
			FileSHA256:    uploaded.FileSHA256,
			FileLength:    length,
		}
		if text != "" {
			message.DocumentMessage.Caption = proto.String(text)
		}
	}
	return message, nil
}

// disconnectChannel unlinks the device from the phone and clears the session
// on the backend, matching the previous bridge's semantics.
func (m *manager) disconnectChannel(ctx context.Context, channelID string) error {
	runtime := m.runtime(channelID)
	if runtime != nil {
		runtime.requestStop()
		m.dropRuntime(runtime)
		if err := runtime.client.Logout(ctx); err != nil {
			m.log.Errorf("channel %s: logout failed: %v", channelID, err)
			runtime.client.Disconnect()
			if runtime.client.Store.ID != nil {
				if err := runtime.client.Store.Delete(ctx); err != nil {
					m.log.Errorf("channel %s: could not delete the stored device: %v", channelID, err)
				}
			}
		}
	}
	return m.api.call(ctx, http.MethodDelete, "/channels/"+channelID+"/auth", nil, nil, 0)
}

func (m *manager) restoreChannels(ctx context.Context) error {
	var channels []struct {
		ID string `json:"id"`
	}
	if err := m.api.call(ctx, http.MethodGet, "/channels", nil, &channels, 0); err != nil {
		return err
	}
	var wg sync.WaitGroup
	for _, channel := range channels {
		wg.Add(1)
		go func(id string) {
			defer wg.Done()
			if err := m.connectChannel(ctx, id); err != nil {
				m.log.Errorf("channel %s: could not restore: %v", id, err)
			}
		}(channel.ID)
	}
	wg.Wait()
	return nil
}

func (m *manager) shutdown() {
	m.mu.Lock()
	runtimes := make([]*channelRuntime, 0, len(m.runtimes))
	for _, runtime := range m.runtimes {
		runtimes = append(runtimes, runtime)
	}
	m.runtimes = make(map[string]*channelRuntime)
	m.mu.Unlock()
	for _, runtime := range runtimes {
		runtime.requestStop()
		runtime.client.Disconnect()
	}
}

func (m *manager) dropRuntime(runtime *channelRuntime) {
	m.mu.Lock()
	if m.runtimes[runtime.channelID] == runtime {
		delete(m.runtimes, runtime.channelID)
	}
	m.mu.Unlock()
}

func (m *manager) statusOrLog(ctx context.Context, channelID, status string, extra map[string]any) {
	if err := m.api.setStatus(ctx, channelID, status, extra); err != nil {
		m.log.Errorf("channel %s: could not report status %s: %v", channelID, status, err)
	}
}

func truncate(value string, limit int) string {
	if len(value) <= limit {
		return value
	}
	return value[:limit]
}
