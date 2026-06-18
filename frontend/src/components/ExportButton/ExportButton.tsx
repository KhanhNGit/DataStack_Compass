
import { Download } from 'lucide-react';
import { useToast } from '../Toast/ToastProvider';

interface ExportButtonProps {
  data: any[];
  columns: string[] | Record<string, string>; // either array of keys or object mapping key -> header label
  filename: string;
  format: 'csv' | 'markdown';
  label?: string; // Optional custom text, defaults to "Export CSV" or "Export Markdown"
  className?: string; // Optional custom styling
  customFormatter?: (data: any[]) => string;
}

export default function ExportButton({
  data,
  columns,
  filename,
  format,
  label,
  className,
  customFormatter,
}: ExportButtonProps) {
  const { success, error } = useToast();

  const handleExport = () => {
    try {
      if (!data || data.length === 0) {
        error('No data to export');
        return;
      }

      let content = '';

      if (customFormatter) {
        content = customFormatter(data);
      } else {
        const isArrayCols = Array.isArray(columns);
        const colKeys = isArrayCols ? columns : Object.keys(columns);
        const colHeaders = isArrayCols ? columns : Object.values(columns);

        if (format === 'csv') {
          // Headers
          content = colHeaders.map((h) => `"${h.replace(/"/g, '""')}"`).join(',') + '\n';

          // Rows
          content += data
            .map((row) =>
              colKeys
                .map((key) => {
                  const val = row[key] !== null && row[key] !== undefined ? String(row[key]) : '';
                  return `"${val.replace(/"/g, '""')}"`;
                })
                .join(',')
            )
            .join('\n');
        } else if (format === 'markdown') {
          // Headers
          content = '| ' + colHeaders.join(' | ') + ' |\n';
          content += '| ' + colHeaders.map(() => '---').join(' | ') + ' |\n';

          // Rows
          content += data
            .map((row) =>
              '| ' +
              colKeys
                .map((key) => {
                  const val = row[key] !== null && row[key] !== undefined ? String(row[key]) : '';
                  return val.replace(/\|/g, '\\|'); // escape pipe
                })
                .join(' | ') +
              ' |'
            )
            .join('\n');
        }
      }

      const mimeType = format === 'csv' ? 'text/csv;charset=utf-8;' : 'text/markdown;charset=utf-8;';
      const blob = new Blob(['\ufeff' + content], { type: mimeType }); // Add BOM for Excel support

      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.setAttribute('href', url);
      link.setAttribute('download', `${filename}.${format === 'csv' ? 'csv' : 'md'}`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);

      success('✓ Export downloaded');
    } catch (err) {
      error('Failed to export data');
      console.error(err);
    }
  };

  return (
    <button
      onClick={handleExport}
      className={className || `
        flex items-center gap-2 px-3 py-1.5 text-sm font-medium
        text-slate-600 bg-transparent hover:bg-slate-100 hover:text-slate-900
        border border-transparent hover:border-slate-200
        rounded-lg transition-all duration-200 whitespace-nowrap
      `}
    >
      <Download size={16} />
      {label || `Export ${format.toUpperCase()}`}
    </button>
  );
}
