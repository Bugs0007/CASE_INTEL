"use client";

import { Eye, MoreVertical, Pencil, Play, Trash2 } from "lucide-react";
import { Menu, MenuItem, MenuList, MenuTrigger } from "@/components/ui/menu";
import { isDocumentActive } from "../document-status-badge";
import { docName } from "./model";
import type { Document } from "@/types";

interface DocumentActionsMenuProps {
  document: Document;
  onProcess: (id: number) => void;
  onDelete: (id: number) => void;
  onEdit: (document: Document) => void;
  onView: (id: number) => void;
}

/** The three dots on a desktop row: View, Edit, Retry/Process, Delete. */
export function DocumentActionsMenu({ document, onProcess, onDelete, onEdit, onView }: DocumentActionsMenuProps) {
  const canProcess =
    !isDocumentActive(document) && (document.processing_status === "pending" || document.processing_status === "failed");
  return (
    <Menu>
      <MenuTrigger
        aria-label={`Actions for ${docName(document)}`}
        onClick={(e) => e.stopPropagation()}
        className="flex h-8 w-8 items-center justify-center rounded-md text-gray-500 hover:bg-[var(--ci-ink-08)] hover:text-gray-900"
      >
        <MoreVertical className="h-4 w-4" aria-hidden="true" />
      </MenuTrigger>
      <MenuList label="Document actions" align="end" className="min-w-[170px]">
        <MenuItem icon={<Eye className="h-4 w-4" />} onSelect={() => onView(document.id)}>
          View
        </MenuItem>
        <MenuItem icon={<Pencil className="h-4 w-4" />} onSelect={() => onEdit(document)}>
          Edit details
        </MenuItem>
        {canProcess && (
          <MenuItem icon={<Play className="h-4 w-4" />} onSelect={() => onProcess(document.id)}>
            {document.processing_status === "failed" ? "Retry processing" : "Process"}
          </MenuItem>
        )}
        <MenuItem icon={<Trash2 className="h-4 w-4" />} className="!text-destructive" onSelect={() => onDelete(document.id)}>
          Delete
        </MenuItem>
      </MenuList>
    </Menu>
  );
}
