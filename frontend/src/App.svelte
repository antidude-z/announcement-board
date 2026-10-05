<script>
  import { onMount } from "svelte";
  import { marked } from "marked";
  import DOMPurify from "dompurify";

  marked.setOptions({
    breaks: true,
    gfm: true
  });

  let session = { authenticated: false, role: null };
  let loadingSession = true;
  let isAdminRoute = false;

  let otpCode = "";
  let adminPassword = "";
  let authError = "";

  let posts = [];
  let page = 1;
  let hasMore = false;
  let loadingPosts = false;

  let searchTerm = "";
  let tagFilter = "";

  let toasts = [];
  let adminTab = "posts";

  let telegramUsers = [];
  let newTelegramId = "";

  let editorOpen = false;
  let form = {
    id: null,
    title: "",
    body_md: "",
    tags: "",
    video_url: ""
  };

  let uploading = false;
  let saving = false;

  function toast(message, kind = "info") {
    const id = Date.now() + Math.random();
    toasts = [...toasts, { id, message, kind }];

    setTimeout(() => {
      toasts = toasts.filter(item => item.id !== id);
    }, 3500);
  }

  function renderMarkdown(body) {
    const raw = marked.parse(body || "");
    return DOMPurify.sanitize(raw, {
      USE_PROFILES: { html: true },
      ADD_ATTR: ["target", "rel"]
    });
  }

  function youtubeId(url) {
    try {
      const u = new URL(url);

      if (u.hostname === "youtu.be") {
        return u.pathname.slice(1);
      }

      if (u.hostname.includes("youtube.com")) {
        if (u.pathname === "/watch") {
          return u.searchParams.get("v");
        }

        if (u.pathname.startsWith("/embed/")) {
          return u.pathname.split("/")[2];
        }
      }

      return null;
    } catch {
      return null;
    }
  }

  function isMp4(url) {
    try {
      const u = new URL(url);
      return ["http:", "https:"].includes(u.protocol) && u.pathname.toLowerCase().endsWith(".mp4");
    } catch {
      return false;
    }
  }

  async function apiFetch(url, options = {}) {
    options.credentials = "include";

    if (options.body && !(options.body instanceof FormData)) {
      options.headers = {
        "Content-Type": "application/json",
        ...(options.headers || {})
      };
      options.body = JSON.stringify(options.body);
    }

    const res = await fetch(url, options);

    if (res.status === 401) {
      session = { authenticated: false, role: null };
    }

    return res;
  }

  async function refreshSession() {
    loadingSession = true;

    try {
      const res = await apiFetch("/api/me");

      if (res.ok) {
        const data = await res.json();
        session = data;

        if (data.authenticated) {
          await loadPosts(true);

          if (data.role === "admin") {
            await loadTelegramUsers();
          }
        }
      } else {
        session = { authenticated: false, role: null };
      }
    } catch {
      session = { authenticated: false, role: null };
    } finally {
      loadingSession = false;
    }
  }

  async function loadPosts(reset = false) {
    if (!session.authenticated) return;

    loadingPosts = true;

    const requestPage = reset ? 1 : page;

    const params = new URLSearchParams({
      page: String(requestPage),
      limit: "10"
    });

    if (searchTerm.trim()) params.set("q", searchTerm.trim());
    if (tagFilter.trim()) params.set("tag", tagFilter.trim());

    try {
      const res = await apiFetch(`/api/posts?${params.toString()}`);

      if (res.ok) {
        const data = await res.json();
        posts = reset ? data.items : [...posts, ...data.items];
        hasMore = data.has_more;
        page = requestPage + 1;
      } else if (res.status !== 401) {
        toast("Unable to load posts.", "error");
      }
    } catch {
      toast("Network error while loading posts.", "error");
    } finally {
      loadingPosts = false;
    }
  }

  async function loadMore() {
    if (!loadingPosts && hasMore) {
      await loadPosts(false);
    }
  }

  async function verifyOtp() {
    authError = "";

    const res = await apiFetch("/api/otp/verify", {
      method: "POST",
      body: { code: otpCode.trim() }
    });

    if (res.ok) {
      otpCode = "";
      await refreshSession();
      toast("Access granted.", "success");
    } else {
      const data = await res.json().catch(() => ({}));
      authError = data.detail || "Invalid passcode.";
    }
  }

  async function loginAdmin() {
    authError = "";

    const res = await apiFetch("/api/admin/login", {
      method: "POST",
      body: { password: adminPassword }
    });

    if (res.ok) {
      adminPassword = "";
      window.location.hash = "#/admin";
      await refreshSession();
      toast("Admin signed in.", "success");
    } else {
      const data = await res.json().catch(() => ({}));
      authError = data.detail || "Invalid admin password.";
    }
  }

  async function logout() {
    await apiFetch("/api/logout", { method: "POST" });
    session = { authenticated: false, role: null };
    posts = [];
    window.location.hash = "";
    toast("Signed out.", "success");
  }

  async function loadTelegramUsers() {
    const res = await apiFetch("/api/telegram-users");

    if (res.ok) {
      const data = await res.json();
      telegramUsers = data.items || [];
    }
  }

  async function addTelegramUser() {
    const parsed = Number(newTelegramId.trim());

    if (!parsed || parsed <= 0) {
      toast("Enter a valid Telegram user ID.", "error");
      return;
    }

    const res = await apiFetch("/api/telegram-users", {
      method: "POST",
      body: { telegram_user_id: parsed }
    });

    if (res.ok) {
      newTelegramId = "";
      await loadTelegramUsers();
      toast("Telegram user added.", "success");
    } else {
      toast("Unable to add Telegram user.", "error");
    }
  }

  async function removeTelegramUser(id) {
    const res = await apiFetch(`/api/telegram-users/${id}`, {
      method: "DELETE"
    });

    if (res.ok) {
      await loadTelegramUsers();
      toast("Telegram user removed.", "success");
    } else {
      toast("Unable to remove Telegram user.", "error");
    }
  }

  function startCreate() {
    editorOpen = true;
    form = {
      id: null,
      title: "",
      body_md: "",
      tags: "",
      video_url: ""
    };
  }

  function startEdit(post) {
    editorOpen = true;
    form = {
      id: post.id,
      title: post.title,
      body_md: post.body_md,
      tags: post.tags,
      video_url: post.video_url
    };
  }

  function cancelEdit() {
    editorOpen = false;
    form = {
      id: null,
      title: "",
      body_md: "",
      tags: "",
      video_url: ""
    };
  }

  async function savePost() {
    if (!form.title.trim() || !form.body_md.trim()) {
      toast("Title and body are required.", "error");
      return;
    }

    saving = true;

    const url = form.id ? `/api/posts/${form.id}` : "/api/posts";
    const method = form.id ? "PUT" : "POST";

    const res = await apiFetch(url, {
      method,
      body: {
        title: form.title,
        body_md: form.body_md,
        tags: form.tags,
        video_url: form.video_url
      }
    });

    saving = false;

    if (res.ok) {
      toast("Announcement saved.", "success");
      cancelEdit();
      await loadPosts(true);
    } else {
      toast("Unable to save announcement.", "error");
    }
  }

  async function deletePost(post) {
    if (!window.confirm(`Delete "${post.title}"?`)) return;

    const res = await apiFetch(`/api/posts/${post.id}`, {
      method: "DELETE"
    });

    if (res.ok) {
      toast("Announcement deleted.", "success");
      await loadPosts(true);
    } else {
      toast("Unable to delete announcement.", "error");
    }
  }

  async function uploadImage(event) {
    const file = event.target.files && event.target.files[0];
    if (!file) return;

    uploading = true;

    const fd = new FormData();
    fd.append("file", file);

    const res = await apiFetch("/api/uploads", {
      method: "POST",
      body: fd
    });

    uploading = false;

    if (res.ok) {
      const data = await res.json();
      form.body_md += `\n![${file.name}](${data.url})\n`;
      toast("Image uploaded.", "success");
    } else {
      toast("Unable to upload image.", "error");
    }

    event.target.value = "";
  }

  onMount(() => {
    isAdminRoute = window.location.hash === "#/admin";

    const onHashChange = () => {
      isAdminRoute = window.location.hash === "#/admin";
    };

    window.addEventListener("hashchange", onHashChange);
    refreshSession();

    return () => {
      window.removeEventListener("hashchange", onHashChange);
    };
  });
</script>

{#if loadingSession}
  <div class="page">
    <div class="glass card center">
      Loading...
    </div>
  </div>
{:else if !session.authenticated}
  <div class="page">
    <div class="auth-wrap">
      <div class="glass auth-card">
        <div class="brand">Announcement Board</div>

        {#if isAdminRoute}
          <p class="muted">Admin sign in</p>

          <form on:submit|preventDefault={loginAdmin} class="stack">
            <input
              type="password"
              placeholder="Admin password"
              bind:value={adminPassword}
              required
            />

            <button type="submit" class="primary">Sign in</button>

            {#if authError}
              <div class="error">{authError}</div>
            {/if}

            <a href="#/">Use one-time passcode</a>
          </form>
        {:else}
          <p class="muted">Enter your one-time passcode</p>

          <form on:submit|preventDefault={verifyOtp} class="stack">
            <input
              type="text"
              placeholder="8-character passcode"
              maxlength="8"
              bind:value={otpCode}
              required
            />

            <button type="submit" class="primary">Enter board</button>

            {#if authError}
              <div class="error">{authError}</div>
            {/if}

            <a href="#/admin">Admin sign in</a>
          </form>
        {/if}
      </div>
    </div>
  </div>
{:else}
  <div class="app">
    <header class="glass topbar">
      <div class="brand">Announcement Board</div>

      <nav>
        {#if session.role === "admin"}
          <button
            class="tab"
            class:active={!isAdminRoute}
            on:click={() => (window.location.hash = "")}
          >
            Feed
          </button>

          <button
            class="tab"
            class:active={isAdminRoute}
            on:click={() => (window.location.hash = "#/admin")}
          >
            Admin
          </button>
        {/if}

        <button class="ghost" on:click={logout}>Logout</button>
      </nav>
    </header>

    <main>
      {#if session.role === "admin" && isAdminRoute}
        <div class="glass panel">
          <div class="tabs">
            <button
              class="tab"
              class:active={adminTab === "posts"}
              on:click={() => (adminTab = "posts")}
            >
              Posts
            </button>

            <button
              class="tab"
              class:active={adminTab === "telegram"}
              on:click={() => {
                adminTab = "telegram";
                loadTelegramUsers();
              }}
            >
              Telegram Access
            </button>
          </div>

          {#if adminTab === "posts"}
            <div class="toolbar">
              <button class="primary" on:click={startCreate}>New announcement</button>
              <button class="ghost" on:click={() => loadPosts(true)}>Refresh</button>
            </div>

            {#if editorOpen}
              <div class="glass card editor">
                <h2>{form.id ? "Edit announcement" : "Create announcement"}</h2>

                <input
                  type="text"
                  placeholder="Title"
                  bind:value={form.title}
                />

                <input
                  type="text"
                  placeholder="Tags, comma separated"
                  bind:value={form.tags}
                />

                <input
                  type="text"
                  placeholder="Video URL: YouTube or MP4"
                  bind:value={form.video_url}
                />

                <textarea
                  placeholder="Markdown body"
                  rows="12"
                  bind:value={form.body_md}
                ></textarea>

                <div class="toolbar">
                  <input
                    type="file"
                    accept="image/png,image/jpeg,image/webp,image/gif"
                    on:change={uploadImage}
                    disabled={uploading}
                  />

                  <button class="primary" on:click={savePost} disabled={saving}>
                    {saving ? "Saving..." : "Save"}
                  </button>

                  <button class="ghost" on:click={cancelEdit}>Cancel</button>
                </div>
              </div>
            {/if}

            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Title</th>
                    <th>Tags</th>
                    <th>Updated</th>
                    <th>Actions</th>
                  </tr>
                </thead>

                <tbody>
                  {#each posts as post (post.id)}
                    <tr>
                      <td>{post.id}</td>
                      <td>{post.title}</td>
                      <td>{post.tags}</td>
                      <td>
                        {post.updated_at
                          ? new Date(post.updated_at).toLocaleString()
                          : new Date(post.created_at).toLocaleString()}
                      </td>
                      <td>
                        <button class="ghost" on:click={() => startEdit(post)}>Edit</button>
                        <button class="danger" on:click={() => deletePost(post)}>Delete</button>
                      </td>
                    </tr>
                  {:else}
                    <tr>
                      <td colspan="5">No posts yet.</td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>

            {#if hasMore}
              <div class="center">
                <button class="ghost" on:click={loadMore} disabled={loadingPosts}>
                  Load more
                </button>
              </div>
            {/if}
          {:else}
            <div class="toolbar">
              <input
                type="text"
                placeholder="Telegram user ID"
                bind:value={newTelegramId}
              />

              <button class="primary" on:click={addTelegramUser}>Add</button>
              <button class="ghost" on:click={loadTelegramUsers}>Refresh</button>
            </div>

            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Telegram ID</th>
                    <th>Username</th>
                    <th>Added</th>
                    <th>Actions</th>
                  </tr>
                </thead>

                <tbody>
                  {#each telegramUsers as user (user.telegram_user_id)}
                    <tr>
                      <td>{user.telegram_user_id}</td>
                      <td>{user.username || "—"}</td>
                      <td>{user.added_at ? new Date(user.added_at).toLocaleString() : "—"}</td>
                      <td>
                        <button
                          class="danger"
                          on:click={() => removeTelegramUser(user.telegram_user_id)}
                        >
                          Remove
                        </button>
                      </td>
                    </tr>
                  {:else}
                    <tr>
                      <td colspan="4">No Telegram users allowlisted yet.</td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          {/if}
        </div>
      {:else}
        <div class="feed-controls glass panel">
          <input
            type="text"
            placeholder="Search posts..."
            bind:value={searchTerm}
            on:keydown={event => {
              if (event.key === "Enter") {
                loadPosts(true);
              }
            }}
          />

          <input
            type="text"
            placeholder="Filter by tag..."
            bind:value={tagFilter}
            on:keydown={event => {
              if (event.key === "Enter") {
                loadPosts(true);
              }
            }}
          />

          <button class="primary" on:click={() => loadPosts(true)}>Apply</button>
          <button
            class="ghost"
            on:click={() => {
              searchTerm = "";
              tagFilter = "";
              loadPosts(true);
            }}
          >
            Clear
          </button>
        </div>

        {#each posts as post (post.id)}
          <article class="glass card post">
            <div class="post-header">
              <h2>{post.title}</h2>
              <div class="meta">
                {new Date(post.created_at).toLocaleString()}
              </div>
            </div>

            {#if post.tags}
              <div class="tags">
                {#each post.tags.split(",").map(tag => tag.trim()).filter(Boolean) as tag}
                  <span class="badge">{tag}</span>
                {/each}
              </div>
            {/if}

            {#if post.video_url}
              {#if youtubeId(post.video_url)}
                <div class="video">
                  <iframe
                    title="YouTube video"
                    src={`https://www.youtube-nocookie.com/embed/${youtubeId(post.video_url)}`}
                    frameborder="0"
                    allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                    allowfullscreen
                  ></iframe>
                </div>
              {:else if isMp4(post.video_url)}
                <video controls src={post.video_url}></video>
              {/if}
            {/if}

            <div class="markdown">
              {@html renderMarkdown(post.body_md)}
            </div>
          </article>
        {:else}
          <div class="glass card center">
            No announcements found.
          </div>
        {/each}

        {#if hasMore}
          <div class="center">
            <button class="ghost" on:click={loadMore} disabled={loadingPosts}>
              Load more
            </button>
          </div>
        {/if}
      {/if}
    </main>
  </div>
{/if}

<div class="toasts">
  {#each toasts as item (item.id)}
    <div class="toast {item.kind}">{item.message}</div>
  {/each}
</div>

<style>
  :global(body) {
    margin: 0;
    font-family: Inter, Geist, ui-sans-serif, system-ui, sans-serif;
    background:
      radial-gradient(circle at top left, rgba(99, 102, 241, 0.16), transparent 30%),
      radial-gradient(circle at top right, rgba(16, 185, 129, 0.08), transparent 20%),
      #0b0d12;
    color: #e5e7eb;
    min-height: 100vh;
  }

  :global(a) {
    color: #818cf8;
    text-decoration: none;
  }

  :global(input),
  :global(textarea) {
    width: 100%;
    box-sizing: border-box;
    border: 1px solid rgba(255, 255, 255, 0.08);
    background: rgba(255, 255, 255, 0.03);
    color: #e5e7eb;
    border-radius: 12px;
    padding: 12px 14px;
    outline: none;
  }

  :global(input:focus),
  :global(textarea:focus) {
    border-color: rgba(99, 102, 241, 0.65);
    box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.12);
  }

  :global(button) {
    border: 1px solid rgba(255, 255, 255, 0.08);
    background: rgba(255, 255, 255, 0.04);
    color: #e5e7eb;
    border-radius: 12px;
    padding: 10px 14px;
    cursor: pointer;
    transition: 0.18s ease;
  }

  :global(button:hover) {
    border-color: rgba(99, 102, 241, 0.45);
    box-shadow: 0 0 18px rgba(99, 102, 241, 0.12);
  }

  :global(button:disabled) {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .page {
    min-height: 100vh;
    display: grid;
    place-items: center;
    padding: 24px;
  }

  .glass {
    background: rgba(18, 21, 30, 0.6);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 18px;
  }

  .card {
    padding: 20px;
  }

  .center {
    display: grid;
    place-items: center;
    margin: 20px 0;
  }

  .auth-wrap {
    width: 100%;
    max-width: 420px;
  }

  .auth-card {
    padding: 28px;
  }

  .brand {
    font-size: 24px;
    font-weight: 700;
    letter-spacing: -0.02em;
    margin-bottom: 12px;
  }

  .muted {
    color: #9ca3af;
    margin-top: 0;
  }

  .stack {
    display: grid;
    gap: 12px;
  }

  .primary {
    background: linear-gradient(135deg, rgba(99, 102, 241, 0.92), rgba(79, 70, 229, 0.92));
    border-color: rgba(99, 102, 241, 0.35);
    color: white;
  }

  .ghost {
    background: transparent;
  }

  .danger {
    background: rgba(244, 63, 94, 0.12);
    border-color: rgba(244, 63, 94, 0.22);
    color: #fda4af;
  }

  .error {
    color: #f43f5e;
    font-size: 14px;
  }

  .app {
    min-height: 100vh;
  }

  .topbar {
    position: sticky;
    top: 12px;
    z-index: 20;
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin: 12px;
    padding: 14px 18px;
  }

  .topbar nav {
    display: flex;
    gap: 10px;
    align-items: center;
    flex-wrap: wrap;
  }

  main {
    padding: 0 12px 32px;
    max-width: 1100px;
    margin: 0 auto;
  }

  .panel {
    padding: 18px;
  }

  .feed-controls {
    display: grid;
    grid-template-columns: 2fr 1fr auto auto;
    gap: 12px;
    padding: 16px;
    margin-bottom: 18px;
  }

  .post {
    margin-bottom: 18px;
    padding: 20px;
  }

  .post-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 16px;
  }

  .post-header h2 {
    margin: 0;
    font-size: 26px;
    line-height: 1.15;
  }

  .meta {
    color: #9ca3af;
    font-size: 13px;
    white-space: nowrap;
    padding-top: 6px;
  }

  .tags {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    margin: 14px 0;
  }

  .badge {
    padding: 5px 9px;
    border-radius: 999px;
    background: rgba(16, 185, 129, 0.12);
    color: #34d399;
    border: 1px solid rgba(16, 185, 129, 0.18);
    font-size: 12px;
  }

  .markdown {
    line-height: 1.65;
  }

  .markdown :global(img) {
    max-width: 100%;
    border-radius: 14px;
    border: 1px solid rgba(255, 255, 255, 0.08);
  }

  .markdown :global(pre) {
    overflow: auto;
    background: rgba(0, 0, 0, 0.22);
    padding: 12px;
    border-radius: 12px;
    border: 1px solid rgba(255, 255, 255, 0.08);
  }

  .markdown :global(code) {
    color: #c7d2fe;
  }

  .video {
    aspect-ratio: 16 / 9;
    margin: 16px 0;
  }

  .video iframe {
    width: 100%;
    height: 100%;
    border: 0;
    border-radius: 14px;
    border: 1px solid rgba(255, 255, 255, 0.08);
  }

  video {
    width: 100%;
    border-radius: 14px;
    border: 1px solid rgba(255, 255, 255, 0.08);
    margin: 16px 0;
  }

  .tabs {
    display: flex;
    gap: 10px;
    margin-bottom: 18px;
    flex-wrap: wrap;
  }

  .tab.active {
    border-color: rgba(99, 102, 241, 0.5);
    box-shadow: 0 0 18px rgba(99, 102, 241, 0.14);
    background: rgba(99, 102, 241, 0.12);
  }

  .toolbar {
    display: flex;
    gap: 12px;
    align-items: center;
    flex-wrap: wrap;
    margin-bottom: 16px;
  }

  .editor {
    display: grid;
    gap: 12px;
    margin-bottom: 18px;
  }

  .table-wrap {
    overflow: auto;
    border-radius: 14px;
    border: 1px solid rgba(255, 255, 255, 0.08);
  }

  table {
    width: 100%;
    border-collapse: collapse;
    min-width: 700px;
  }

  th,
  td {
    padding: 12px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    text-align: left;
  }

  th {
    color: #9ca3af;
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  td button {
    margin-right: 8px;
  }

  .toasts {
    position: fixed;
    right: 16px;
    bottom: 16px;
    display: grid;
    gap: 10px;
    z-index: 50;
  }

  .toast {
    padding: 12px 14px;
    border-radius: 12px;
    border: 1px solid rgba(255, 255, 255, 0.08);
    background: rgba(18, 21, 30, 0.88);
    backdrop-filter: blur(12px);
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.25);
  }

  .toast.success {
    border-color: rgba(16, 185, 129, 0.22);
    color: #6ee7b7;
  }

  .toast.error {
    border-color: rgba(244, 63, 94, 0.22);
    color: #fda4af;
  }

  @media (max-width: 800px) {
    .feed-controls {
      grid-template-columns: 1fr;
    }

    .post-header {
      flex-direction: column;
    }
  }
</style>