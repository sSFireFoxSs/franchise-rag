const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export function postChat(question, brandMnno, conversationId, signal) {
  const body = { question };

  if (brandMnno) {
    body.brand_mnno = brandMnno;
  }

  if (conversationId !== null && conversationId !== undefined) {
    body.conversation_id = conversationId;
  }

  return authRequest("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
}

export function getConversations() {
  return authRequest("/api/conversations");
}

export function getConversation(conversationId) {
  return authRequest(`/api/conversations/${conversationId}`);
}


async function authRequest(path, options = {}) {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    credentials: "include",
  });

  if (!res.ok) {
    let message = `서버 오류 (${res.status})`;

    try {
      const data = await res.json();
      if (data?.detail) {
        message = data.detail;
      }
    } catch {
      // JSON 오류 응답이 아니면 기본 메시지를 사용한다.
    }

    throw new Error(message);
  }

  if (res.status === 204) {
    return null;
  }

  return res.json();
}

export function signup(email, password, passwordConfirm) {
  return authRequest("/api/auth/signup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email,
      password,
      password_confirm: passwordConfirm,
    }),
  });
}

export function login(email, password) {
  return authRequest("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email,
      password,
    }),
  });
}

export async function getMe() {
  const res = await fetch(`${API_BASE_URL}/api/auth/me`, {
    credentials: "include",
  });

  if (res.status === 401) {
    return null;
  }

  if (!res.ok) {
    throw new Error(`서버 오류 (${res.status})`);
  }

  return res.json();
}

export function logout() {
  return authRequest("/api/auth/logout", {
    method: "POST",
  });
}

export async function getTop20(by = "sales", category = null) {
  const params = new URLSearchParams({ by });
  if (category) params.set("category", category);

  const res = await fetch(
    `${API_BASE_URL}/api/brands/top20?${params.toString()}`,
    {
      cache: "no-store",
    }
  );

  if (!res.ok) {
    throw new Error(`서버 오류 (${res.status})`);
  }

  return res.json();
}

export async function getHomeStats() {
  const res = await fetch(`${API_BASE_URL}/api/home/stats`, {
    cache: "no-store",
  });

  if (!res.ok) {
    throw new Error(`서버 오류 (${res.status})`);
  }

  return res.json();
}

export async function getTop20Categories() {
  const res = await fetch(`${API_BASE_URL}/api/brands/top20/categories`, {
    cache: "no-store",
  });

  if (!res.ok) {
    throw new Error(`서버 오류 (${res.status})`);
  }

  return res.json();
}

// brands: [{ name, mnno? }, ...] — 2~4개. mnno가 있으면(자동완성으로 고른 경우) 그걸 그대로
// 쓰고, 없으면 백엔드가 name으로 resolve한다. 응답: { brands: [entry, ...] } (입력 순서 유지).
export async function getCompare(brands) {
  const params = new URLSearchParams();

  for (const b of brands) {
    params.append("name", b.name);
    params.append("mnno", b.mnno || "");
  }

  const res = await fetch(
    `${API_BASE_URL}/api/brands/compare?${params.toString()}`,
    {
      cache: "no-store",
    }
  );

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail || `서버 오류 (${res.status})`);
  }

  return res.json();
}

export async function searchBrands(q, limit = 8) {
  const params = new URLSearchParams({
    q,
    limit: String(limit),
  });

  const res = await fetch(
    `${API_BASE_URL}/api/brands/search?${params.toString()}`,
    {
      cache: "no-store",
    }
  );

  if (!res.ok) {
    throw new Error(`서버 오류 (${res.status})`);
  }

  return res.json();
}