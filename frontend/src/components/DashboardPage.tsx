"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import Workspace from "@/app/workspace";
import { ApiError, api } from "@/lib/api";

export default function DashboardPage() {
  const router = useRouter();
  const [authorized, setAuthorized] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void api("/me")
        .then(() => setAuthorized(true))
        .catch(error => {
          if (error instanceof ApiError && error.status === 401) router.replace("/login");
          else setError(true);
        });
    }, 0);
    return () => window.clearTimeout(timer);
  }, [router]);

  if (authorized) return <Workspace />;
  if (error) return <main className="portal-loading" role="alert">We couldn’t verify your session. Please try again.</main>;
  return <main className="portal-loading" role="status">Loading your secure workspace…</main>;
}
