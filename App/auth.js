// Auth gate: decides which of the three screens (#login-gate,
// #access-denied, #app-shell) is visible, and only ever calls startApp()
// (see app.js) with data that actually came back from a Supabase query --
// the app never reads any local/static dataset file.
//
// Security note: this file only controls what the UI *shows*. The real
// access control is server-side, in Postgres Row Level Security on
// Supabase (see Scripts/supabase/001_schema.sql) -- the dataset_snapshot
// query below returns zero rows for anyone not on the allowed_users
// allowlist, regardless of what this script does or doesn't hide.

const sb = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

const screens = {
  login: document.getElementById("login-gate"),
  denied: document.getElementById("access-denied"),
  app: document.getElementById("app-shell"),
};

function showScreen(name) {
  Object.entries(screens).forEach(([key, el]) => {
    if (el) el.hidden = key !== name;
  });
}

async function loadForSession(session) {
  const email = session.user.email;

  const { data, error } = await sb
    .from("dataset_snapshot")
    .select("payload")
    .eq("id", 1)
    .maybeSingle();

  if (error || !data) {
    if (error) console.error("Dataset query failed:", error.message);
    const deniedEmail = document.getElementById("denied-email");
    if (deniedEmail) deniedEmail.textContent = email;
    showScreen("denied");
    return;
  }

  const accountEmail = document.getElementById("account-email");
  if (accountEmail) accountEmail.textContent = email;
  showScreen("app");
  startApp(data.payload);
}

sb.auth.onAuthStateChange((_event, session) => {
  if (session) {
    loadForSession(session);
  } else {
    resetApp();
    showScreen("login");
  }
});

document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const email = document.getElementById("login-email").value.trim();
  const password = document.getElementById("login-password").value;
  const errorEl = document.getElementById("login-error");
  const submitBtn = document.getElementById("login-submit");

  errorEl.hidden = true;
  submitBtn.disabled = true;
  submitBtn.textContent = "Signing in…";

  const { error } = await sb.auth.signInWithPassword({ email, password });

  submitBtn.disabled = false;
  submitBtn.textContent = "Sign in";

  if (error) {
    errorEl.textContent = error.message;
    errorEl.hidden = false;
  }
});

async function signOut() {
  await sb.auth.signOut();
}

document.getElementById("signout-button").addEventListener("click", signOut);
document.getElementById("denied-signout").addEventListener("click", signOut);
