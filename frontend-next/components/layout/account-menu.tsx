"use client";

import { useEffect, useState } from "react";
import { ChevronUp, LogOut, Settings } from "lucide-react";
import { Menu, MenuHeader, MenuItem, MenuList, MenuTrigger } from "@/components/ui/menu";
import { useLogout } from "@/hooks/use-logout";
import { getUsername } from "@/lib/auth";

function Avatar({ name, className }: { name: string; className: string }) {
  return (
    <span
      aria-hidden="true"
      className={`flex flex-shrink-0 items-center justify-center rounded-full bg-[var(--ci-paper)] font-bold text-[color:var(--ci-ink)] ${className}`}
    >
      {(name.trim().charAt(0) || "A").toUpperCase()}
    </span>
  );
}

/** Who is signed in, with Settings and Log out. In the sidebar it is the
 * pinned bottom row and opens upward; below `lg` (no sidebar) it is an
 * avatar in the top bar. */
export function AccountMenu({ variant }: { variant: "sidebar" | "avatar" }) {
  const [username, setUsername] = useState<string | null>(null);
  const logout = useLogout();

  // localStorage is not there during SSR, and the name is only ever set at
  // login, so it is read once on mount.
  useEffect(() => {
    setUsername(getUsername());
  }, []);

  const name = username || "Advocate";
  const sidebar = variant === "sidebar";

  return (
    <Menu>
      {sidebar ? (
        <MenuTrigger
          aria-label="Account menu"
          className="flex h-[46px] w-full items-center gap-2.5 rounded-md px-2.5 text-[13.5px] font-semibold text-[color:var(--ci-on-field)] hover:bg-[var(--ci-field-2)]"
        >
          <Avatar name={name} className="h-[30px] w-[30px] text-[12.5px]" />
          <span className="min-w-0 flex-1 truncate text-left">{name}</span>
          <ChevronUp className="h-3.5 w-3.5 opacity-60" strokeWidth={2} />
        </MenuTrigger>
      ) : (
        <MenuTrigger
          aria-label="Account menu"
          title={name}
          className="flex h-11 w-11 items-center justify-center rounded-full"
        >
          <Avatar name={name} className="h-9 w-9 text-sm" />
        </MenuTrigger>
      )}
      <MenuList
        label="Account"
        placement={sidebar ? "above" : "below"}
        align={sidebar ? "start" : "end"}
        className={sidebar ? "right-0" : undefined}
      >
        <MenuHeader>
          <span className="text-sm font-bold">{name}</span>
          <span className="block text-xs text-gray-500">Signed in</span>
        </MenuHeader>
        <MenuItem icon={<Settings className="h-4 w-4" />} href="/settings">
          Settings
        </MenuItem>
        <MenuItem icon={<LogOut className="h-4 w-4" />} onSelect={logout}>
          Log out
        </MenuItem>
      </MenuList>
    </Menu>
  );
}
