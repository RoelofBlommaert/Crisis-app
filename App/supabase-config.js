// Public Supabase project configuration -- safe to be public.
// This is the project URL + anon/public key, not a secret: access to
// data is enforced by Postgres Row Level Security policies on the
// Supabase side (see Scripts/supabase/001_schema.sql), not by keeping
// this file hidden. Never put a service_role key or DB password here.
const SUPABASE_URL = "https://simedrvlkgtrxhmagmow.supabase.co";
const SUPABASE_ANON_KEY =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNpbWVkcnZsa2d0cnhobWFnbW93Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODk0NTQwNzMsImV4cCI6MjEwNTAzMDA3M30.REskoTeThoFzPZJPkRic0mWPuw4UB96qGCuxsvnHNkU";
