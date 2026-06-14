import React from 'react';
import { Database, ShieldAlert, FileText, PlayCircle } from 'lucide-react';

interface EmptyStateProps {
  icon: React.ReactNode;
  title: string;
  description: string;
  action?: React.ReactNode;
  className?: string;
}

export function EmptyState({ icon, title, description, action, className = '' }: EmptyStateProps) {
  return (
    <div className={`py-16 text-center flex flex-col items-center justify-center ${className}`}>
      <div className="text-slate-300 mb-4">{icon}</div>
      <h3 className="text-sm font-semibold text-slate-700">{title}</h3>
      <p className="text-sm text-slate-500 mt-2 max-w-sm">{description}</p>
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}

EmptyState.NoToolsFound = function NoToolsFound({ className }: { className?: string }) {
  return (
    <EmptyState
      icon={<Database size={40} />}
      title="No tools found"
      description="No tools match your search. Try different keywords."
      className={className}
    />
  );
};

EmptyState.NoCVEsFound = function NoCVEsFound({ days = 30, className }: { days?: number, className?: string }) {
  return (
    <EmptyState
      icon={<ShieldAlert size={40} className="text-emerald-300" />}
      title="No CVEs found"
      description={`No CVEs found in the last ${days} days. Your stack looks clean! ✓`}
      className={className}
    />
  );
};

EmptyState.NoBulletins = function NoBulletins({ className }: { className?: string }) {
  return (
    <EmptyState
      icon={<FileText size={40} />}
      title="No security bulletins"
      description="No security bulletins yet."
      className={className}
    />
  );
};

EmptyState.PipelineNotRun = function PipelineNotRun({ className, onRun }: { className?: string, onRun?: () => void }) {
  return (
    <EmptyState
      icon={<PlayCircle size={40} className="text-indigo-300" />}
      title="Pipeline not run yet"
      description="It looks like data hasn't been ingested yet. Run your first DAG in Airflow."
      action={
        onRun && (
          <button onClick={onRun} className="h-9 px-4 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 transition-colors shadow-sm">
            Run Pipeline
          </button>
        )
      }
      className={className}
    />
  );
};
