"use client";

import { Briefcase, ChevronDown, Plus, Upload } from "lucide-react";
import { Menu, MenuItem, MenuList, MenuTrigger } from "@/components/ui/menu";
import { useDialogs } from "@/providers/dialog-provider";

/** The one "New" menu: a case or a document. Both entries open the same
 * shared dialogs the rest of the app uses. */
export function NewMenu({ variant }: { variant: "sidebar" | "icon" }) {
  const { openNewCaseChooser, openUploadDocument } = useDialogs();
  const sidebar = variant === "sidebar";

  return (
    <Menu>
      {sidebar ? (
        // ci-btn--solid flips to paper-on-ink inside .ci-on-field, which is
        // the light surface this button wants on the dark sidebar.
        <MenuTrigger className="ci-btn ci-btn--solid h-10 w-full justify-start !px-3 !py-0 text-sm font-semibold">
          <Plus className="h-4 w-4" strokeWidth={2} />
          <span>New</span>
          <ChevronDown className="ml-auto h-3.5 w-3.5 opacity-70" strokeWidth={2} />
        </MenuTrigger>
      ) : (
        <MenuTrigger
          aria-label="New"
          title="New"
          className="ci-btn ci-btn--line h-11 w-11 justify-center !p-0"
        >
          <Plus className="h-[18px] w-[18px]" strokeWidth={1.8} />
        </MenuTrigger>
      )}
      <MenuList
        label="New"
        placement="below"
        align={sidebar ? "start" : "end"}
        className={sidebar ? "min-w-0 right-0" : undefined}
      >
        <MenuItem icon={<Briefcase className="h-4 w-4" />} hint="N" onSelect={openNewCaseChooser}>
          New case
        </MenuItem>
        <MenuItem icon={<Upload className="h-4 w-4" />} hint="U" onSelect={openUploadDocument}>
          Upload document
        </MenuItem>
      </MenuList>
    </Menu>
  );
}
