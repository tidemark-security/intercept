import React from "react";

interface ModalShellProps {
  children: React.ReactNode;
}

export function ModalShell({ children }: ModalShellProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
      <div className="w-full max-w-lg rounded-md bg-neutral-100 px-6 py-6">
        <div className="flex w-full flex-col items-start gap-6">{children}</div>
      </div>
    </div>
  );
}
