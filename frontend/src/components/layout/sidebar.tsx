import { NavLink } from "react-router-dom";
import { FlaskConical } from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [{ to: "/", label: "Domains", icon: FlaskConical }];

export function Sidebar() {
  return (
    <aside className="w-56 border-r bg-background flex flex-col py-4">
      <nav className="flex flex-col gap-1 px-3">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-secondary text-foreground"
                  : "text-muted-foreground hover:bg-secondary/50 hover:text-foreground",
              )
            }
          >
            <item.icon className="h-4 w-4" />
            {item.label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
