import { DocumentRow } from "./document-row";
import type { Document } from "@/types";

interface DocumentTableProps {
  documents: Document[];
  isLoading?: boolean;
  onProcess: (id: number) => void;
  onDelete: (id: number) => void;
  onEdit: (document: Document) => void;
  onView: (id: number) => void;
  processingId?: number;
  deletingId?: number;
  viewingId?: number;
}

export function DocumentTable({
  documents,
  isLoading,
  onProcess,
  onDelete,
  onEdit,
  onView,
  processingId,
  deletingId,
  viewingId,
}: DocumentTableProps) {
  if (isLoading) {
    return (
      <div className="bg-white border border-gray-100 rounded-xl overflow-hidden">
        <div className="p-12 text-center text-gray-500">
          Loading documents...
        </div>
      </div>
    );
  }

  if (documents.length === 0) {
    return (
      <div className="bg-white border border-gray-100 rounded-xl overflow-hidden">
        <div className="p-12 text-center">
          <div className="text-6xl mb-4">📄</div>
          <h3 className="text-lg font-medium text-gray-900 mb-2">
            No documents found
          </h3>
          <p className="text-gray-500">
            Upload a document or try adjusting your filters.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2.5">
      {documents.map((doc) => (
        <DocumentRow
          key={doc.id}
          document={doc}
          onProcess={onProcess}
          onDelete={onDelete}
          onEdit={onEdit}
          onView={onView}
          isProcessing={processingId === doc.id}
          isDeleting={deletingId === doc.id}
          isViewing={viewingId === doc.id}
        />
      ))}
    </div>
  );
}
