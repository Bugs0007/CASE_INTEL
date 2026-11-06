"use client";

import { HelpCircle, Keyboard } from "lucide-react";
import { Menu, MenuItem, MenuList, MenuTrigger } from "@/components/ui/menu";
import { WALKTHROUGH_ENABLED } from "@/lib/feature-flags";
import { useDialogs } from "@/providers/dialog-provider";

/** The round "?" in the top bar: the guided tour and the shortcut list. */
export function HelpMenu() {
  const { openShortcuts } = useDialogs();

  return (
    <Menu>
      <MenuTrigger
        aria-label="Help"
        title="Help"
        className="ci-btn ci-btn--line h-9 w-9 justify-center !rounded-full !p-0 text-[15px] font-semibold"
      >
        ?
      </MenuTrigger>
      <MenuList label="Help" align="end">
        {WALKTHROUGH_ENABLED && (
          <MenuItem icon={<HelpCircle className="h-4 w-4" />} href="/walkthrough">
            Guided tour
          </MenuItem>
        )}
        <MenuItem icon={<Keyboard className="h-4 w-4" />} hint="?" onSelect={openShortcuts}>
          Keyboard shortcuts
        </MenuItem>
      </MenuList>
    </Menu>
  );
}
