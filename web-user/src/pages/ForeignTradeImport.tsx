import { FileSpreadsheet } from 'lucide-react';
import SectionPlaceholder from './SectionPlaceholder';

export default function ForeignTradeImport() {
  return (
    <SectionPlaceholder
      icon={FileSpreadsheet}
      accent="#f59e0b"
      title="表格导入"
      description="通过 CSV / XLSX 批量导入公司客户与跨境人才线索：下载模板、字段映射、入库前预检，并自动进行关键词 / LLM 评分与分级。"
    />
  );
}
