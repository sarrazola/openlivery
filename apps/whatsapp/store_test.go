package main

import "testing"

func TestNormalizeStoreURL(t *testing.T) {
	cases := []struct{ in, schema, want string }{
		{"postgres://u:p@h:5432/db", "", "postgres://u:p@h:5432/db"},
		{"postgresql://u:p@h/db", "whatsmeow", "postgres://u:p@h/db?search_path=whatsmeow"},
		{"postgresql+psycopg://u:p@h/db?sslmode=require", "whatsmeow", "postgres://u:p@h/db?sslmode=require&search_path=whatsmeow"},
		{"postgres://u:p@h/db?search_path=other", "whatsmeow", "postgres://u:p@h/db?search_path=other"},
		{"file:whatsmeow.db", "whatsmeow", "file:whatsmeow.db"},
	}
	for _, c := range cases {
		if got := normalizeStoreURL(c.in, c.schema); got != c.want {
			t.Fatalf("normalizeStoreURL(%q, %q) = %q, want %q", c.in, c.schema, got, c.want)
		}
	}
}
