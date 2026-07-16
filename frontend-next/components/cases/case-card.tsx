"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { StatusBadge, PriorityBadge } from "@/components/ui/badge";
import { Eye, MoreVertical, FileText, MessageSquare, Mail, Trash2 } from "lucide-react";
import { formatDate } from "@/lib/utils";
import type { Case } from "@/types";

interface CaseCardProps {
  case: Case;
  onDelete?: (id: number) => void;
  isDeleting?: boolean;
}

export function CaseCard({ case: caseItem, onDelete, isDeleting }: CaseCardProps) {
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isMenuOpen) return;

    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setIsMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isMenuOpen]);

  return (
    <Card className="hover:shadow-md transition-shadow">
      <CardContent className="p-6">
        {/* Header */}
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-2">
            <StatusBadge status={caseItem.status} />
            <PriorityBadge priority={caseItem.priority} />
          </div>
          <div className="relative" ref={menuRef}>
            <Button
              variant="ghost"
              size="sm"
              className="p-1 h-8 w-8"
              onClick={() => setIsMenuOpen((open) => !open)}
              aria-haspopup="true"
              aria-expanded={isMenuOpen}
              aria-label="Case options"
            >
              <MoreVertical className="h-4 w-4" />
            </Button>
            {isMenuOpen && (
              <div
                role="menu"
                className="absolute right-0 top-full mt-1 w-40 bg-white rounded-lg shadow-lg border border-gray-100 py-1 z-10"
              >
                <button
                  role="menuitem"
                  disabled={isDeleting}
                  onClick={() => {
                    setIsMenuOpen(false);
                    onDelete?.(caseItem.id);
                  }}
                  className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-600 hover:bg-red-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  <Trash2 className="h-4 w-4" />
                  {isDeleting ? "Deleting..." : "Delete Case"}
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Case Info */}
        <div className="mb-4">
          <div className="text-xs text-gray-500 font-mono mb-1">
            {caseItem.case_number}
          </div>
          <h3 className="font-semibold text-gray-900 text-lg mb-2 line-clamp-2">
            {caseItem.title}
          </h3>
          {caseItem.case_type && (
            <span className="inline-block px-2 py-1 text-xs bg-blue-100 text-blue-800 rounded-md mb-2">
              {caseItem.case_type}
            </span>
          )}
        </div>

        {/* Client vs Opposing */}
        <div className="mb-4 space-y-1">
          <div className="text-sm">
            <span className="text-gray-500">Client:</span>{" "}
            <span className="text-gray-900 font-medium">
              {caseItem.client_name}
            </span>
          </div>
          {caseItem.opposing_party && (
            <div className="text-sm">
              <span className="text-gray-500">vs:</span>{" "}
              <span className="text-gray-900">{caseItem.opposing_party}</span>
            </div>
          )}
        </div>

        {/* Meta Counts */}
        <div className="flex items-center gap-4 mb-4 text-sm text-gray-500">
          <div className="flex items-center gap-1">
            <FileText className="h-4 w-4" />
            <span>{caseItem.document_count} docs</span>
          </div>
          <div className="flex items-center gap-1">
            <Mail className="h-4 w-4" />
            <span>{caseItem.thread_count} threads</span>
          </div>
          <div className="flex items-center gap-1">
            <MessageSquare className="h-4 w-4" />
            <span>{caseItem.conversation_count} chats</span>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between pt-4 border-t border-gray-100">
          <div className="text-xs text-gray-500">
            Created {formatDate(caseItem.created_at, "MMM d")}
          </div>
          <Link href={`/cases/${caseItem.id}`}>
            <Button variant="secondary" size="sm">
              <Eye className="h-4 w-4" />
              View Details
            </Button>
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}
