package main

import (
	"context"
	"database/sql"
	"flag"
	"fmt"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"regexp"
	"strings"
	"syscall"
	"time"

	_ "github.com/lib/pq"
	sqlite "modernc.org/sqlite"

	"go.mau.fi/whatsmeow/store/sqlstore"
	waLog "go.mau.fi/whatsmeow/util/log"
)

var schemaName = regexp.MustCompile(`^[A-Za-z_][A-Za-z0-9_]*$`)

func getenv(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

// loadDotEnv fills the environment from the first .env found next to or above
// the working directory, without overriding variables that are already set.
// This mirrors what the previous bridge did for local development.
func loadDotEnv() {
	for _, path := range []string{".env", "../.env", "../../.env"} {
		data, err := os.ReadFile(path)
		if err != nil {
			continue
		}
		for _, line := range strings.Split(string(data), "\n") {
			line = strings.TrimSpace(line)
			if line == "" || strings.HasPrefix(line, "#") {
				continue
			}
			key, value, found := strings.Cut(line, "=")
			if !found {
				continue
			}
			key = strings.TrimSpace(key)
			value = strings.Trim(strings.TrimSpace(value), `"'`)
			if key != "" && os.Getenv(key) == "" {
				os.Setenv(key, value)
			}
		}
		return
	}
}

// openStore opens the whatsmeow session store. A postgres:// URL uses
// Postgres (the search_path query parameter selects the schema, which is
// created when missing); anything else is treated as a SQLite path.
func openStore(ctx context.Context, storeURL string, log waLog.Logger) (*sqlstore.Container, error) {
	if strings.HasPrefix(storeURL, "postgres://") || strings.HasPrefix(storeURL, "postgresql://") {
		ensureSchema(storeURL, log)
		return sqlstore.New(ctx, "postgres", storeURL, log)
	}
	dsn := storeURL
	if !strings.HasPrefix(dsn, "file:") {
		dsn = "file:" + dsn
	}
	if !strings.Contains(dsn, "_pragma=") {
		separator := "?"
		if strings.Contains(dsn, "?") {
			separator = "&"
		}
		dsn += separator + "_pragma=foreign_keys(1)&_pragma=busy_timeout(10000)"
	}
	return sqlstore.New(ctx, "sqlite3", dsn, log)
}

func ensureSchema(storeURL string, log waLog.Logger) {
	parsed, err := url.Parse(storeURL)
	if err != nil {
		return
	}
	schema := parsed.Query().Get("search_path")
	if schema == "" || !schemaName.MatchString(schema) {
		return
	}
	db, err := sql.Open("postgres", storeURL)
	if err != nil {
		return
	}
	defer db.Close()
	if _, err := db.Exec("CREATE SCHEMA IF NOT EXISTS " + schema); err != nil {
		// A restricted role cannot create schemas; assume it already exists.
		log.Debugf("could not create schema %s: %v", schema, err)
	}
}

func healthcheck(port string) int {
	client := &http.Client{Timeout: 5 * time.Second}
	response, err := client.Get("http://127.0.0.1:" + port + "/health")
	if err != nil || response.StatusCode != http.StatusOK {
		return 1
	}
	response.Body.Close()
	return 0
}

func main() {
	check := flag.Bool("healthcheck", false, "probe the local /health endpoint and exit")
	flag.Parse()
	loadDotEnv()

	port := getenv("WHATSAPP_BRIDGE_PORT", "3101")
	if *check {
		os.Exit(healthcheck(port))
	}

	host := getenv("WHATSAPP_BRIDGE_HOST", "127.0.0.1")
	token := getenv("WHATSAPP_BRIDGE_TOKEN", "dev-local-change-this-bridge-token")
	backendURL := strings.TrimRight(getenv("BACKEND_URL", "http://localhost:8000"), "/")
	storeURL := getenv("WHATSAPP_STORE_URL", "file:whatsmeow.db")
	logLevel := getenv("WHATSAPP_LOG_LEVEL", "ERROR")

	// whatsmeow's sqlstore expects the sqlite3 driver name; register the pure
	// Go driver under it so builds stay CGO-free.
	if !driverRegistered("sqlite3") {
		sql.Register("sqlite3", &sqlite.Driver{})
	}

	log := waLog.Stdout("Bridge", strings.ToUpper(logLevel), false)
	ctx := context.Background()
	container, err := openStore(ctx, storeURL, log.Sub("Store"))
	if err != nil {
		fmt.Fprintln(os.Stderr, "[WhatsApp] Could not open the session store:", err)
		os.Exit(1)
	}

	api := newBackendClient(backendURL, token)
	channels := newManager(api, container, log)

	server := &http.Server{
		Addr:    net.JoinHostPort(host, port),
		Handler: newHandler(managerActions{manager: channels}, token),
	}
	go func() {
		fmt.Printf("[WhatsApp] Bridge ready at %s:%s\n", host, port)
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			fmt.Fprintln(os.Stderr, "[WhatsApp] Server error:", err)
			os.Exit(1)
		}
	}()
	go func() {
		if err := channels.restoreChannels(ctx); err != nil {
			fmt.Fprintln(os.Stderr, "[WhatsApp] Could not restore sessions:", err)
		}
	}()

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)
	<-stop
	channels.shutdown()
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	_ = server.Shutdown(shutdownCtx)
}

func driverRegistered(name string) bool {
	for _, driver := range sql.Drivers() {
		if driver == name {
			return true
		}
	}
	return false
}
