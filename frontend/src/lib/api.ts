export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    ...options,
    credentials: "same-origin",
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });
  let data: Record<string, unknown> = {};
  try {
    data = await response.json() as Record<string, unknown>;
  } catch {
    if (response.ok) return undefined as T;
  }
  if (!response.ok) {
    const detail = data.detail;
    const message = typeof detail === "string"
      ? detail
      : Array.isArray(detail)
        ? detail.map(item => typeof item === "object" && item && "msg" in item ? String(item.msg) : "Invalid form value").join(". ")
        : "The request could not be completed.";
    throw new ApiError(message, response.status);
  }
  return data as T;
}

export const json = (body: unknown): Pick<RequestInit, "method" | "body"> => ({
  method: "POST",
  body: JSON.stringify(body),
});
