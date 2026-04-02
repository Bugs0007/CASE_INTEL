import Link from "next/link";
import { Download, Trash2, Play, Loader2, Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { formatDate, getFileIcon } from "@/lib/utils";
import type { Document } from "@/types";

interface DocumentRowProps {
  document: Document;
  onProcess: (id: number) => void;
  onDelete: (id: number) => void;
  onEdit: (document: Document) => void;
  isProcessing?: boolean;
  isDeleting?: boolean;
}

export function DocumentRow({
  document,
  onProcess,
  onDelete,
  onEdit,
  isProcessing,
  isDeleting,
}: DocumentRowProps) {
  const fileIcon = getFileIcon(document.file_type);

  return (
    <tr className="border-b border-gray-100 hover:bg-gray-50 transition-colors">
      {/* Name */}
      <td className="py-4 px-6">
        <div className="flex items-center gap-3">
          <span className="text-xl flex-shrink-0">{fileIcon}</span>
          <div className="min-w-0">
            <div className="font-medium text-gray-900 truncate">
              {document.filename}
            </div>
            <div className="text-xs text-gray-500 capitalize">
              {document.document_type}
            </div>
          </div>
        </div>
      </td>

      {/* Case */}
      <td className="py-4 px-6">
        {document.case ? (
          <Link
            href={`/cases/${document.case.id}`}
            className="text-blue-600 hover:text-blue-800 hover:underline"
          >
            <div className="font-medium">{document.case.case_number}</div>
            <div className="text-xs text-gray-500 truncate max-w-xs">
              {document.case.title}
            </div>
          </Link>
        ) : (
          <span className="text-gray-400">No case</span>
        )}
      </td>

      {/* Date */}
      <td className="py-4 px-6 text-sm text-gray-600">
        {formatDate(document.document_date || document.created_at, "MMM d, yyyy")}
      </td>

      {/* AI Insight */}
      <td className="py-4 px-6">
        {document.ai_summary ? (
          <div className="text-sm text-gray-700 line-clamp-2 max-w-md">
            {document.ai_summary}
          </div>
        ) : (
          <span className="text-xs text-gray-400 italic">
            {document.processing_status === "pending"
              ? "Not processed yet"
              : document.processing_status === "processing"
                ? "Processing..."
                : "No insight available"}
          </span>
        )}
      </td>

      {/* Status */}
      <td className="py-4 px-6">
        <span
          className={`inline-block px-2 py-1 text-xs rounded-md font-medium ${
            document.processing_status === "completed"
              ? "bg-green-100 text-green-800"
              : document.processing_status === "processing"
                ? "bg-blue-100 text-blue-800"
                : document.processing_status === "failed"
                  ? "bg-red-100 text-red-800"
                  : "bg-gray-100 text-gray-600"
          }`}
        >
          {document.processing_status}
        </span>
      </td>

      {/* Actions */}
      <td className="py-4 px-6">
        <div className="flex items-center gap-2">
          {document.processing_status === "pending" && (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => onProcess(document.id)}
              disabled={isProcessing}
            >
              {isProcessing ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Play className="h-4 w-4" />
              )}
              {isProcessing ? "Processing..." : "Process"}
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            className="p-1 h-8 w-8"
            onClick={() => onEdit(document)}
            title="Edit"
          >
            <Pencil className="h-4 w-4 text-gray-600" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="p-1 h-8 w-8"
            title="Download"
          >
            <Download className="h-4 w-4 text-gray-600" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="p-1 h-8 w-8"
            onClick={() => onDelete(document.id)}
            disabled={isDeleting}
            title="Delete"
          >
            <Trash2 className="h-4 w-4 text-red-500" />
          </Button>
        </div>
      </td>
    </tr>
  );
}
