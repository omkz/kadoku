import type {Metadata} from "next";
import AdminDashboard from "@/components/AdminDashboard";
import "./admin.css";

export const metadata: Metadata = {
  title: "Kadoku Admin — Store management",
  description: "Private management area for Kadoku's demo catalog and Sandbox orders.",
  robots: {index:false, follow:false},
};

export default function AdminPage() {
  return <AdminDashboard/>;
}
