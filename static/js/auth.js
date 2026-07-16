(() => {
  const config = window.authConfig || {};

  function emit(event, detail) {
    document.dispatchEvent(new CustomEvent(`auth:${event}`, { detail }));
  }

  if (!config.enabled || !config.clientId) {
    window.requireAuth = () => Promise.resolve(null);
    window.renderAuthButton = () => {};
    window.authClient = {
      isEnabled: false,
      getUser: () => null,
      signOut: () => Promise.resolve(),
    };
    emit("change", { authenticated: true });
    return;
  }

  const state = {
    user: null,
    readyPromise: null,
    readyResolve: null,
    pendingButtons: [],
  };

  state.readyPromise = new Promise((resolve) => {
    state.readyResolve = resolve;
  });

  window.requireAuth = () => state.readyPromise;

  function setAuthenticated(user) {
    state.user = user;
    if (state.readyResolve) {
      state.readyResolve(user);
      state.readyResolve = null;
    }
    emit("change", { authenticated: true, user });
  }

  function setUnauthenticated(reason) {
    state.user = null;
    emit("change", { authenticated: false, reason });
    emit("required", {});
  }

  function ensureGoogleReady(callback) {
    if (window.google && window.google.accounts && window.google.accounts.id) {
      callback();
      return;
    }
    window.setTimeout(() => ensureGoogleReady(callback), 80);
  }

  function renderButton(target) {
    if (!target) {
      return;
    }
    if (window.google && window.google.accounts && window.google.accounts.id) {
      target.innerHTML = "";
      window.google.accounts.id.renderButton(target, {
        type: "standard",
        theme: "outline",
        size: "large",
        width: 320,
      });
    } else {
      state.pendingButtons.push(target);
    }
  }

  function flushPendingButtons() {
    if (!(window.google && window.google.accounts && window.google.accounts.id)) {
      return;
    }
    const targets = [...state.pendingButtons];
    state.pendingButtons.length = 0;
    targets.forEach((target) => renderButton(target));
  }

  window.renderAuthButton = (target) => {
    const element = typeof target === "string" ? document.querySelector(target) : target;
    renderButton(element);
  };

  async function handleCredentialResponse(payload) {
    const endpoint = config.loginEndpoint || "/auth/login";
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ credential: payload.credential }),
        credentials: "include",
      });
      if (!response.ok) {
        throw new Error("Authentication failed.");
      }
      const data = await response.json();
      setAuthenticated(data);
      emit("login", { user: data });
    } catch (error) {
      console.error("Google login failed", error);
      setUnauthenticated(error);
      emit("error", { error });
      window.setTimeout(() => {
        if (
          window.google &&
          window.google.accounts &&
          window.google.accounts.id &&
          typeof window.google.accounts.id.prompt === "function"
        ) {
          window.google.accounts.id.prompt();
        }
      }, 200);
    }
  }

  function initGoogle() {
    ensureGoogleReady(() => {
      window.google.accounts.id.initialize({
        client_id: config.clientId,
        callback: handleCredentialResponse,
        auto_select: false,
        cancel_on_tap_outside: true,
      });
      flushPendingButtons();
      emit("ready", {});
    });
  }

  async function fetchSession() {
    const endpoint = config.sessionEndpoint || "/auth/session";
    try {
      const response = await fetch(endpoint, { credentials: "include" });
      if (response.ok) {
        const data = await response.json();
        setAuthenticated(data);
        return;
      }
    } catch (error) {
      console.warn("Session lookup failed", error);
    }
    setUnauthenticated();
    initGoogle();
  }

  window.authClient = {
    isEnabled: true,
    getUser: () => state.user,
    signOut: async () => {
      try {
        await fetch(config.logoutEndpoint || "/auth/logout", {
          method: "POST",
          credentials: "include",
        });
      } finally {
        state.user = null;
        setUnauthenticated();
        window.location.reload();
      }
    },
  };

  fetchSession();
})();
