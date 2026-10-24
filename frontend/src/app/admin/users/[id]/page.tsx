"use client";
import { useParams } from "next/navigation";
import AdminPage from "@/components/AdminPage";
export default function Page() {
  const params = useParams<{ id: string }>();
  return <AdminPage section="users" userId={params.id} />;
}
