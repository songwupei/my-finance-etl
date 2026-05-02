"""DuckDB数据仓库实现，支持Parquet到DuckDB的自动同步和优化查询。"""
import duckdb
import polars as pl
import pandas as pd
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime


class DuckDBDataWarehouse:
    """DuckDB数据仓库管理器，实现三层存储架构的查询层。"""

    def __init__(self, parameters: dict = None, db_path: str = None):
        """初始化DuckDB数据仓库。

        Args:
            parameters: 全局参数字典，从中读取 database.path
            db_path: DuckDB数据库文件路径（优先级高于parameters）
        """
        if db_path:
            self.db_path = db_path
        elif parameters:
            self.db_path = parameters["database"]["path"]
        else:
            self.db_path = "data/warehouse/finance.duckdb"
        self.db_dir = Path(self.db_path).parent
        self.db_dir.mkdir(parents=True, exist_ok=True)

        self.logger = logging.getLogger(__name__)
        self.conn = None
        self._connect()

    def _connect(self):
        """连接到DuckDB数据库。"""
        try:
            self.conn = duckdb.connect(self.db_path)
            self.conn.execute("SET enable_progress_bar=false;")
            self.logger.info(f"已连接到DuckDB: {self.db_path}")
        except Exception as e:
            self.logger.error(f"连接DuckDB失败: {e}")
            raise

    def create_schema(self):
        """创建数据仓库schema。"""
        self.logger.info("创建DuckDB数据仓库schema...")

        # 创建schema - 使用不会与database名称冲突的名称
        self.conn.execute("CREATE SCHEMA IF NOT EXISTS finance_data;")

        # 创建系统表记录元数据
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS finance_data.metadata (
                key VARCHAR PRIMARY KEY,
                value VARCHAR,
                updated_at TIMESTAMP
            )
        """)

        self.logger.info("DuckDB schema创建完成")

    def load_dimension_from_parquet(self, table_name: str, parquet_path: str,
                                   primary_key: Optional[str] = None) -> None:
        """从Parquet文件加载维度表到DuckDB。

        Args:
            table_name: 表名（如dim_unit_report）
            parquet_path: Parquet文件路径
            primary_key: 主键列名（可选）
        """
        self.logger.info(f"从Parquet加载维度表: {table_name}")

        # 使用COPY FROM PARQUET语法高效加载
        self.conn.execute(f"""
            CREATE OR REPLACE TABLE finance_data.{table_name} AS
            SELECT * FROM read_parquet('{parquet_path}')
        """)

        # 如果有主键，创建索引（如果不是唯一列则创建普通索引）
        if primary_key:
            try:
                self.conn.execute(f"""
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_{table_name}_{primary_key}
                    ON finance_data.{table_name}({primary_key})
                """)
                self.logger.info(f"创建唯一索引: {table_name}.{primary_key}")
            except Exception as idx_error:
                self.logger.warning(f"无法创建唯一索引 {table_name}.{primary_key}: {idx_error}")
                self.logger.warning(f"创建普通索引替代...")
                self.conn.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_{table_name}_{primary_key}
                    ON finance_data.{table_name}({primary_key})
                """)

        # 收集统计信息
        self.conn.execute(f"ANALYZE finance_data.{table_name}")

        # 记录表统计信息
        result = self.conn.execute(f"""
            SELECT COUNT(*) as row_count FROM finance_data.{table_name}
        """).fetchone()
        self.logger.info(f"表 {table_name} 加载完成: {result[0]} 行")

    def load_fact_from_parquet(self, table_name: str, parquet_path: str,
                              indexes: List[str] = None) -> None:
        """从Parquet文件加载事实表到DuckDB。

        Args:
            table_name: 表名（如fact_finance_data）
            parquet_path: Parquet文件路径
            indexes: 需要创建的索引列列表
        """
        self.logger.info(f"从Parquet加载事实表: {table_name}")

        # 加载事实表
        self.conn.execute(f"""
            CREATE OR REPLACE TABLE finance_data.{table_name} AS
            SELECT * FROM read_parquet('{parquet_path}')
        """)

        # 为查询性能创建索引
        if indexes:
            for idx_col in indexes:
                self.conn.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_{table_name}_{idx_col}
                    ON finance_data.{table_name}({idx_col})
                """)

        # 收集统计信息
        self.conn.execute(f"ANALYZE finance_data.{table_name}")

        # 记录表统计信息
        result = self.conn.execute(f"""
            SELECT COUNT(*) as row_count FROM finance_data.{table_name}
        """).fetchone()
        self.logger.info(f"表 {table_name} 加载完成: {result[0]} 行")

    def load_all_tables(self, parquet_base_path: str = "data/03_primary") -> None:
        """从指定路径加载所有Parquet表到DuckDB。

        Args:
            parquet_base_path: Parquet文件基础路径
        """
        base_path = Path(parquet_base_path)

        # 维度表配置
        dimension_config = [
            ("dim_unit_report", "entity_report_id"),
            ("dim_caliber", "caliber_id"),
            ("dim_report_category", "category_id"),
            ("dim_period", "period_id"),
            ("dim_standard_account", "account_code"),
            ("dim_organization_tree", "node_id"),
        ]

        # 事实表配置
        fact_config = [
            ("fact_finance_data", ["entity_report_id", "period_id", "account_code"]),
        ]

        # 加载维度表
        for table_name, primary_key in dimension_config:
            parquet_file = base_path / f"{table_name}.parquet"
            if parquet_file.exists():
                self.load_dimension_from_parquet(table_name, str(parquet_file), primary_key)
            else:
                self.logger.warning(f"Parquet文件不存在: {parquet_file}")

        # 加载事实表
        for table_name, indexes in fact_config:
            parquet_file = base_path / f"{table_name}.parquet"
            if parquet_file.exists():
                self.load_fact_from_parquet(table_name, str(parquet_file), indexes)
            else:
                self.logger.warning(f"Parquet文件不存在: {parquet_file}")

    def load_treasury_tables(
        self,
        dim_treasury_account: pd.DataFrame,
        dim_treasury_account_type: pd.DataFrame,
        fact_treasury_account_balance: pd.DataFrame,
    ) -> None:
        """直接加载司库 DataFrame 到 DuckDB 表。"""
        self.logger.info("加载司库表到 DuckDB...")

        self.conn.execute("CREATE SCHEMA IF NOT EXISTS finance_data;")

        if not dim_treasury_account.empty:
            self.conn.execute("CREATE OR REPLACE TABLE finance_data.dim_treasury_account AS SELECT * FROM dim_treasury_account")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_ta_entity ON finance_data.dim_treasury_account(entity_report_id)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_ta_number ON finance_data.dim_treasury_account(account_number)")
            self.conn.execute("ANALYZE finance_data.dim_treasury_account")
            self.logger.info(f"  dim_treasury_account: {len(dim_treasury_account)} rows")

        if not dim_treasury_account_type.empty:
            self.conn.execute("CREATE OR REPLACE TABLE finance_data.dim_treasury_account_type AS SELECT * FROM dim_treasury_account_type")
            self.logger.info(f"  dim_treasury_account_type: {len(dim_treasury_account_type)} rows")

        if not fact_treasury_account_balance.empty:
            self.conn.execute("CREATE OR REPLACE TABLE finance_data.fact_treasury_account_balance AS SELECT * FROM fact_treasury_account_balance")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_fab_entity ON finance_data.fact_treasury_account_balance(entity_report_id)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_fab_period ON finance_data.fact_treasury_account_balance(period)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_fab_account ON finance_data.fact_treasury_account_balance(account_id)")
            self.conn.execute("ANALYZE finance_data.fact_treasury_account_balance")
            self.logger.info(f"  fact_treasury_account_balance: {len(fact_treasury_account_balance)} rows")

    def optimize_for_analytical_queries(self) -> None:
        """为分析查询优化DuckDB数据库。"""
        self.logger.info("优化DuckDB数据库性能...")

        try:
            # 1. 设置数据库参数
            self.conn.execute("""
                SET memory_limit='2GB';
                SET threads=4;
                SET enable_object_cache=true;
            """)

            # 2. 检查需要的表是否存在
            required_tables = ['fact_finance_data', 'dim_period', 'dim_unit_report', 'dim_organization_tree']
            existing_tables = self.conn.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'finance_data'
            """).fetchall()

            existing_table_names = [t[0] for t in existing_tables]
            self.logger.info(f"现有表: {existing_table_names}")

            # 3. 如果fact_finance_data和dim_period存在，创建月度汇总视图
            if 'fact_finance_data' in existing_table_names and 'dim_period' in existing_table_names:
                if 'dim_unit_report' in existing_table_names:
                    self.conn.execute("""
                        CREATE VIEW IF NOT EXISTS finance_data.v_monthly_summary AS
                        SELECT
                            p.period_name,
                            u.unit_name,
                            COALESCE(c.category_name, 'unknown') as category_name,
                            SUM(f.value) as total_value,
                            AVG(f.value) as avg_value,
                            COUNT(*) as record_count
                        FROM finance_data.fact_finance_data f
                        LEFT JOIN finance_data.dim_period p ON f.period_id = p.period_id
                        LEFT JOIN finance_data.dim_unit_report u ON f.entity_report_id = u.entity_report_id
                        LEFT JOIN finance_data.dim_report_category c ON f.category_id = c.category_id
                        GROUP BY p.period_name, u.unit_name, COALESCE(c.category_name, 'unknown')
                        ORDER BY p.period_name DESC, total_value DESC
                    """)
                    self.logger.info("创建月度汇总视图")

            # 4. 如果dim_organization_tree存在，创建组织层级视图
            if 'dim_organization_tree' in existing_table_names:
                self.conn.execute("""
                    CREATE VIEW IF NOT EXISTS finance_data.v_organization_hierarchy AS
                    WITH RECURSIVE org_hierarchy AS (
                        -- 根节点
                        SELECT
                            node_id,
                            parent_id,
                            node_name,
                            0 as level,
                            node_id as root_id
                        FROM finance_data.dim_organization_tree
                        WHERE parent_id = '#'

                        UNION ALL

                        -- 子节点
                        SELECT
                            t.node_id,
                            t.parent_id,
                            t.node_name,
                            h.level + 1 as level,
                            h.root_id
                        FROM finance_data.dim_organization_tree t
                        JOIN org_hierarchy h ON t.parent_id = h.node_id
                    )
                    SELECT * FROM org_hierarchy
                    ORDER BY root_id, level, node_id
                """)
                self.logger.info("创建组织层级视图")

            # 5. 为所有表收集统计信息
            for table_name in existing_table_names:
                try:
                    self.conn.execute(f"ANALYZE finance_data.{table_name}")
                except Exception as e:
                    self.logger.warning(f"无法分析表 {table_name}: {e}")

            self.logger.info("DuckDB优化完成")

        except Exception as e:
            self.logger.warning(f"数据库优化失败: {e}")

    def execute_query(self, query: str) -> pd.DataFrame:
        """执行SQL查询并返回Pandas DataFrame。

        Args:
            query: SQL查询语句

        Returns:
            查询结果的Pandas DataFrame
        """
        try:
            return self.conn.execute(query).fetch_df()
        except Exception as e:
            self.logger.error(f"查询执行失败: {e}\n查询: {query}")
            raise

    def get_database_stats(self) -> Dict[str, Any]:
        """获取数据库统计信息。"""
        stats = {}

        # 表列表
        tables_result = self.conn.execute("""
            SELECT table_name, table_type
            FROM information_schema.tables
            WHERE table_schema = 'finance_data'
            ORDER BY table_name
        """).fetchall()

        stats["tables"] = []
        for table_name, table_type in tables_result:
            # 每个表的行数
            count_result = self.conn.execute(f"""
                SELECT COUNT(*) FROM finance_data.{table_name}
            """).fetchone()

            stats["tables"].append({
                "name": table_name,
                "type": table_type,
                "row_count": count_result[0] if count_result else 0
            })

        # 数据库大小
        db_size = Path(self.db_path).stat().st_size if Path(self.db_path).exists() else 0
        stats["database_size_mb"] = db_size / (1024 * 1024)

        # 最后更新时间
        stats["last_updated"] = datetime.now().isoformat()

        return stats

    def backup_to_parquet(self, backup_dir: str = "data/backup/duckdb") -> None:
        """将DuckDB表备份到Parquet文件。

        Args:
            backup_dir: 备份目录
        """
        backup_path = Path(backup_dir)
        backup_path.mkdir(parents=True, exist_ok=True)

        self.logger.info(f"备份DuckDB表到Parquet: {backup_dir}")

        # 获取所有表
        tables_result = self.conn.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'finance_data'
        """).fetchall()

        for (table_name,) in tables_result:
            backup_file = backup_path / f"{table_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.parquet"

            # 导出到Parquet
            self.conn.execute(f"""
                COPY (SELECT * FROM finance_data.{table_name})
                TO '{backup_file}' (FORMAT PARQUET)
            """)

            self.logger.info(f"  表 {table_name} 备份到: {backup_file}")

        self.logger.info(f"备份完成: {len(tables_result)} 个表")

    def close(self):
        """关闭DuckDB连接。"""
        if self.conn:
            self.conn.close()
            self.logger.info("DuckDB连接已关闭")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# 工具函数
def load_to_duckdb_warehouse(
    dim_unit_report: pd.DataFrame,
    dim_caliber: pd.DataFrame,
    dim_report_category: pd.DataFrame,
    dim_period: pd.DataFrame,
    dim_standard_account: pd.DataFrame,
    dim_organization_tree: pd.DataFrame,
    fact_finance_data: pd.DataFrame,
) -> tuple:
    """加载所有维度表和事实表到DuckDB数据仓库。

    注意：此函数通过Parquet中间文件加载到DuckDB，而不是直接写入。
    真正的DuckDB加载在后续步骤中由DuckDBDataWarehouse.load_all_tables()完成。
    """
    # 这里只是传递数据框，实际的DuckDB加载在后续处理中
    # 在完整的pipeline中，会先保存到Parquet，然后加载到DuckDB

    return (
        dim_unit_report,
        dim_caliber,
        dim_report_category,
        dim_period,
        dim_standard_account,
        dim_organization_tree,
        fact_finance_data,
    )


def create_duckdb_pipeline(**kwargs):
    """创建DuckDB数据仓库加载pipeline（供测试使用）。"""
    from kedro.pipeline import Pipeline, node

    return Pipeline([
        node(
            func=load_to_duckdb_warehouse,
            inputs=[
                "dim_unit_report",
                "dim_caliber",
                "dim_report_category",
                "dim_period",
                "dim_standard_account",
                "dim_organization_tree",
                "fact_finance_data",
            ],
            outputs=[
                "loaded_dim_unit_report",
                "loaded_dim_caliber",
                "loaded_dim_report_category",
                "loaded_dim_period",
                "loaded_dim_standard_account",
                "loaded_dim_organization_tree",
                "loaded_fact_finance_data",
            ],
            name="load_to_duckdb_warehouse",
        )
    ])