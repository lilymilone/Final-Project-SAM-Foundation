/**
 * Tiny fetch wrapper. The session lives in an HttpOnly cookie the browser
 * sends automatically. No keys or tokens are ever stored in JavaScript or
 * localStorage. State-changing calls carry the X-SAM-Request header the
 * server requires as a same-origin check.
 */
export class ApiError extends Error {
  constructor(public status: number, message: string, public detail: unknown = null) {
    super(message);
  }
}

type Listener = () => void;
const unauthorizedListeners = new Set<Listener>();
export const onUnauthorized = (fn: Listener) => {
  unauthorizedListeners.add(fn);
  return () => {
    unauthorizedListeners.delete(fn);
  };
};

function detailMessage(body: unknown, status: number): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object" && "message" in detail && typeof (detail as { message: unknown }).message === "string") {
      return (detail as { message: string }).message;
    }
    if (Array.isArray(detail) && detail[0]?.msg) {
      const field = detail[0].loc?.slice(-1)[0];
      return field ? `${String(field).replace(/_/g, " ")}: ${detail[0].msg}` : detail[0].msg;
    }
  }
  if (status >= 500) return "Something went wrong on our side. Please try again.";
  return "Request failed.";
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, headers, ...rest } = init;
  const method = (rest.method ?? (json !== undefined ? "POST" : "GET")).toUpperCase();
  let response: Response;
  try {
    response = await fetch(path, {
      ...rest,
      method,
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        ...(json !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(method !== "GET" ? { "X-SAM-Request": "1" } : {}),
        ...headers,
      },
      body: json !== undefined ? JSON.stringify(json) : rest.body,
    });
  } catch {
    throw new ApiError(0, "Can't reach the SAM SPACE server. Is it running?");
  }
  const body = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith("/api/auth/login")) {
      unauthorizedListeners.forEach((fn) => fn());
    }
    throw new ApiError(response.status, detailMessage(body, response.status),
      body && typeof body === "object" && "detail" in body ? (body as { detail: unknown }).detail : null);
  }
  return body as T;
}
