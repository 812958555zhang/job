"""
SQLite 数据库操作封装模块

提供 DatabaseHelper 类用于管理 SQLite 数据库连接和 CRUD 操作，
包含 profiles（用户画像）、applications（求职记录）、
conversations（对话历史）三张核心表的完整操作。
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 配置日志记录器
logger = logging.getLogger(__name__)

# 需要序列化为 JSON 存储的列表字段
_JSON_FIELDS = {
    "skills", "core_competencies", "projects",
    "expected_positions", "expected_locations"
}


class DatabaseHelper:
    """
    SQLite 数据库操作封装类

    功能：
    - 数据库连接管理（自动创建、重连机制）
    - 表结构初始化（首次启动自动建表）
    - 三张核心表的 CRUD 操作
    - 事务管理和异常处理
    """

    def __init__(self, db_path: str = "data/job_assistant.db"):
        """
        初始化数据库连接

        Args:
            db_path: 数据库文件路径（默认 data/job_assistant.db）
        """
        self.db_path: str = db_path
        self._connection: Optional[sqlite3.Connection] = None

        # 确保数据库所在目录存在
        db_path_obj = Path(db_path)
        db_path_obj.parent.mkdir(parents=True, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        """
        获取数据库连接（支持自动重连）

        通过检测连接有效性实现断线重连机制，
        确保每次获取到的连接都是可用的。

        Returns:
            sqlite3.Connection 对象，支持列名访问
        """
        try:
            # 检查现有连接是否有效
            if self._connection is not None:
                # 执行简单查询验证连接状态
                self._connection.execute("SELECT 1")
                return self._connection
        except sqlite3.Error:
            # 连接已失效，关闭后重新创建
            self._close_connection()

        # 创建新连接并配置
        self._connection = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            timeout=10.0
        )
        # 设置行工厂，支持通过列名访问数据
        self._connection.row_factory = sqlite3.Row
        # 启用外键约束
        self._connection.execute("PRAGMA foreign_keys = ON")
        logger.info("数据库连接已建立: %s", self.db_path)
        return self._connection

    def _close_connection(self):
        """内部方法：安全关闭数据库连接"""
        if self._connection is not None:
            try:
                self._connection.close()
            except sqlite3.Error as e:
                logger.warning("关闭数据库连接时出错: %s", e)
            finally:
                self._connection = None

    def initialize_database(self):
        """
        初始化数据库表结构（如果表不存在则创建）

        创建三张核心表及其索引：
        - profiles: 用户画像表
        - applications: 求职记录表
        - conversations: 对话历史表
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        # 用户画像表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT,
                email TEXT,
                education TEXT NOT NULL,
                major TEXT,
                school TEXT,
                total_experience_years REAL NOT NULL,
                current_position TEXT,
                current_company TEXT,
                skills TEXT,
                core_competencies TEXT,
                projects TEXT,
                expected_positions TEXT,
                expected_salary_min INTEGER,
                expected_salary_max INTEGER,
                expected_locations TEXT,
                resume_file_path TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 求职记录表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL UNIQUE,
                job_name TEXT NOT NULL,
                company_name TEXT NOT NULL,
                salary_min INTEGER,
                salary_max INTEGER,
                location TEXT,
                job_description TEXT,
                match_score REAL NOT NULL,
                match_reason TEXT,
                greeting_message TEXT,
                status TEXT DEFAULT 'pending',
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_reply_at TIMESTAMP,
                reply_count INTEGER DEFAULT 0,
                notes TEXT
            )
        """)

        # 对话历史表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                application_id INTEGER,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                message_type TEXT DEFAULT 'text',
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                job_id TEXT,
                is_sent INTEGER NOT NULL,
                ai_generated INTEGER DEFAULT 0,
                FOREIGN KEY (application_id) REFERENCES applications(id)
            )
        """)

        # 创建索引加速常用查询
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_conv_conversation_id
            ON conversations(conversation_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_conv_application_id
            ON conversations(application_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_app_status
            ON applications(status)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_app_job_id
            ON applications(job_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_app_applied_at
            ON applications(applied_at)
        """)

        conn.commit()
        logger.info("数据库表结构初始化完成")

    def close(self):
        """关闭数据库连接，释放资源"""
        self._close_connection()
        logger.info("数据库连接已关闭")

    # ==================== 工具方法 ====================

    @staticmethod
    def _serialize_data(data: Dict[str, Any]) -> Dict[str, Any]:
        """
        序列化数据中的列表字段为 JSON 字符串

        Args:
            data: 原始数据字典

        Returns:
            处理后的数据字典（列表字段转为 JSON 字符串）
        """
        result = data.copy()
        for field in _JSON_FIELDS:
            if field in result and isinstance(result[field], (list, dict)):
                result[field] = json.dumps(result[field], ensure_ascii=False)
        return result

    @staticmethod
    def _deserialize_row(row: sqlite3.Row) -> Dict[str, Any]:
        """
        反序列化行数据中的 JSON 字段为 Python 对象

        Args:
            row: 数据库行对象

        Returns:
            处理后的字典（JSON 字符段还原为列表/字典）
        """
        result = dict(row)
        for field in _JSON_FIELDS:
            if field in result and result[field] is not None:
                try:
                    result[field] = json.loads(result[field])
                except (json.JSONDecodeError, TypeError):
                    # JSON 解析失败时保留原始字符串
                    pass
        return result

    def _dict_to_insert(
        self, data: Dict[str, Any], table: str
    ) -> Tuple[str, List[Any]]:
        """
        将字典转换为 INSERT 语句的占位符和参数值

        Args:
            data: 待插入的数据字典
            table: 目标表名

        Returns:
            (SQL 语句片段, 参数值列表) 元组
        """
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        return sql, list(data.values())

    def _dict_to_update(
        self, data: Dict[str, Any], table: str, condition: str
    ) -> Tuple[str, List[Any]]:
        """
        将字典转换为 UPDATE 语句的 SET 子句和参数值

        Args:
            data: 待更新的数据字典
            table: 目标表名
            condition: WHERE 条件子句

        Returns:
            (完整 SQL 语句, 参数值列表) 元组
        """
        set_clause = ", ".join([f"{k} = ?" for k in data.keys()])
        # 仅 profiles 表包含 updated_at 字段，其他表不追加
        if table == "profiles":
            sql = f"UPDATE {table} SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE {condition}"
        else:
            sql = f"UPDATE {table} SET {set_clause} WHERE {condition}"
        return sql, list(data.values())

    # ==================== Profiles 表操作 ====================

    def create_profile(self, profile_data: Dict[str, Any]) -> int:
        """
        创建用户画像记录

        Args:
            profile_data: 用户画像字段字典

        Returns:
            新插入记录的自增 ID

        Raises:
            sqlite3.Error: 数据库操作失败时抛出
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        serialized = self._serialize_data(profile_data)
        sql, params = self._dict_to_insert(serialized, "profiles")

        try:
            cursor.execute(sql, params)
            conn.commit()
            profile_id: int = cursor.lastrowid
            logger.info("用户画像创建成功, ID=%d", profile_id)
            return profile_id
        except sqlite3.Error as e:
            conn.rollback()
            logger.error("创建用户画像失败: %s", e)
            raise

    def get_profile(self, profile_id: int = 1) -> Optional[Dict[str, Any]]:
        """
        获取单条用户画像记录

        默认获取 ID=1 的活跃画像（当前使用的画像）。

        Args:
            profile_id: 画像主键 ID

        Returns:
            画像字典，不存在则返回 None
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM profiles WHERE id = ?", (profile_id,)
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return self._deserialize_row(row)

    def update_profile(
        self, profile_id: int, profile_data: Dict[str, Any]
    ) -> bool:
        """
        更新用户画像信息

        Args:
            profile_id: 画像主键 ID
            profile_data: 需要更新的字段字典

        Returns:
            更新成功返回 True，记录不存在返回 False
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        serialized = self._serialize_data(profile_data)
        sql, params = self._dict_to_update(serialized, "profiles", "id = ?")
        params.append(profile_id)

        try:
            cursor.execute(sql, params)
            conn.commit()
            success: bool = cursor.rowcount > 0
            if success:
                logger.info("用户画像更新成功, ID=%d", profile_id)
            return success
        except sqlite3.Error as e:
            conn.rollback()
            logger.error("更新用户画像失败: %s", e)
            raise

    def list_profiles(self) -> List[Dict[str, Any]]:
        """
        列出所有用户画像记录

        Returns:
            画像字典列表，按创建时间倒序排列
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM profiles ORDER BY created_at DESC")
        rows = cursor.fetchall()
        return [self._deserialize_row(row) for row in rows]

    def delete_profile(self, profile_id: int) -> bool:
        """
        删除指定用户画像

        Args:
            profile_id: 画像主键 ID

        Returns:
            删除成功返回 True，记录不存在返回 False
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "DELETE FROM profiles WHERE id = ?", (profile_id,)
            )
            conn.commit()
            success: bool = cursor.rowcount > 0
            if success:
                logger.info("用户画像删除成功, ID=%d", profile_id)
            return success
        except sqlite3.Error as e:
            conn.rollback()
            logger.error("删除用户画像失败: %s", e)
            raise

    # ==================== Applications 表操作 ====================

    def create_application(self, app_data: Dict[str, Any]) -> int:
        """
        创建求职申请记录

        Args:
            app_data: 求职记录字段字典

        Returns:
            新插入记录的自增 ID

        Raises:
            sqlite3.Error: 数据库操作失败时抛出
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        sql, params = self._dict_to_insert(app_data, "applications")

        try:
            cursor.execute(sql, params)
            conn.commit()
            record_id: int = cursor.lastrowid
            logger.info("求职记录创建成功, ID=%d, job_id=%s", record_id, app_data.get("job_id"))
            return record_id
        except sqlite3.IntegrityError as e:
            conn.rollback()
            logger.warning("岗位已存在(重复申请), job_id=%s: %s", app_data.get("job_id"), e)
            raise
        except sqlite3.Error as e:
            conn.rollback()
            logger.error("创建求职记录失败: %s", e)
            raise

    def get_application(self, record_id: int) -> Optional[Dict[str, Any]]:
        """
        获取单条求职记录详情

        Args:
            record_id: 记录主键 ID

        Returns:
            记录字典，不存在则返回 None
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM applications WHERE id = ?", (record_id,)
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    def update_application(
        self, record_id: int, app_data: Dict[str, Any]
    ) -> bool:
        """
        更新求职记录信息

        Args:
            record_id: 记录主键 ID
            app_data: 需要更新的字段字典

        Returns:
            更新成功返回 True，记录不存在返回 False
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        sql, params = self._dict_to_update(app_data, "applications", "id = ?")
        params.append(record_id)

        try:
            cursor.execute(sql, params)
            conn.commit()
            success: bool = cursor.rowcount > 0
            if success:
                logger.info("求职记录更新成功, ID=%d", record_id)
            return success
        except sqlite3.Error as e:
            conn.rollback()
            logger.error("更新求职记录失败: %s", e)
            raise

    def list_applications(
        self,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        查询求职记录列表（支持按状态筛选和分页）

        Args:
            status: 按 status 字段筛选（可选）
            limit: 返回数量上限
            offset: 分页偏移量

        Returns:
            记录字典列表，按申请时间倒序
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        query = "SELECT * FROM applications"
        params: List[Any] = []

        if status is not None:
            query += " WHERE status = ?"
            params.append(status)

        query += " ORDER BY applied_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def get_today_stats(self) -> Dict[str, int]:
        """
        获取今日求职统计数据

        统计当天各状态的记录数量。

        Returns:
            包含统计结果的字典：
            - total: 总沟通数
            - sent: 已发送数
            - replied: 已回复数
            - skipped: 跳过数
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        today: str = datetime.now().strftime("%Y-%m-%d")

        # 统计今日总沟通数
        cursor.execute(
            "SELECT COUNT(*) FROM applications WHERE DATE(applied_at) = ?",
            (today,),
        )
        total: int = cursor.fetchone()[0]

        # 按状态分组统计
        cursor.execute(
            """SELECT status, COUNT(*) FROM applications
               WHERE DATE(applied_at) = ?
               GROUP BY status""",
            (today,),
        )
        status_counts: Dict[str, int] = dict(cursor.fetchall())

        return {
            "total": total,
            "sent": status_counts.get("sent", 0),
            "replied": status_counts.get("replied", 0),
            "skipped": status_counts.get("skipped", 0),
        }

    def check_job_applied(self, job_id: str) -> bool:
        """
        检查某岗位是否已被申请过（去重校验）

        Args:
            job_id: 岗位唯一标识

        Returns:
            已存在记录返回 True，否则返回 False
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            "SELECT COUNT(*) FROM applications WHERE job_id = ?", (job_id,)
        )
        count: int = cursor.fetchone()[0]
        return count > 0

    # ==================== Conversations 表操作 ====================

    def create_conversation(self, conv_data: Dict[str, Any]) -> int:
        """
        创建新的对话会话记录

        Args:
            conv_data: 对话数据字典，需包含 conversation_id、role、content、is_sent 等字段

        Returns:
            新记录的自增 ID

        Raises:
            sqlite3.Error: 数据库操作失败时抛出
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        sql, params = self._dict_to_insert(conv_data, "conversations")

        try:
            cursor.execute(sql, params)
            conn.commit()
            record_id: int = cursor.lastrowid
            logger.info("对话记录创建成功, ID=%d", record_id)
            return record_id
        except sqlite3.Error as e:
            conn.rollback()
            logger.error("创建对话记录失败: %s", e)
            raise

    def add_message(
        self, conversation_id: int, message_data: Dict[str, Any]
    ) -> int:
        """
        向已有会话中追加一条消息

        Args:
            conversation_id: 会话主键 ID
            message_data: 消息内容字典，需包含 role、content、is_sent 等字段

        Returns:
            新消息记录的自增 ID

        Raises:
            sqlite3.Error: 数据库操作失败时抛出
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        # 将 conversation_id 合入消息数据
        full_data = {"conversation_id": conversation_id, **message_data}
        sql, params = self._dict_to_insert(full_data, "conversations")

        try:
            cursor.execute(sql, params)
            conn.commit()
            message_id: int = cursor.lastrowid
            logger.info("消息添加成功, ID=%d, conversation_id=%d", message_id, conversation_id)
            return message_id
        except sqlite3.Error as e:
            conn.rollback()
            logger.error("添加消息失败: %s", e)
            raise

    def get_conversation_messages(
        self, conversation_id: int, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        获取指定会话的消息列表（按时间正序排列）

        Args:
            conversation_id: 会话 ID
            limit: 返回消息数量上限

        Returns:
            消息字典列表
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """SELECT * FROM conversations
               WHERE conversation_id = ?
               ORDER BY timestamp ASC LIMIT ?""",
            (conversation_id, limit),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def get_recent_conversations(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取最近的对话会话列表（含最新消息预览）

        通过子查询获取每个会话的最新消息作为预览内容。

        Args:
            limit: 返回会话数量上限

        Returns:
            会话摘要列表
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """SELECT c.conversation_id, c.application_id, c.job_id,
                      MAX(c.timestamp) as last_message_time,
                      (SELECT content FROM conversations c2
                       WHERE c2.conversation_id = c.conversation_id
                       ORDER BY c2.timestamp DESC LIMIT 1) as last_message
               FROM conversations c
               GROUP BY c.conversation_id
               ORDER BY last_message_time DESC
               LIMIT ?""",
            (limit,),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]


# ==================== 全局单例访问接口 ====================

_db_instance: Optional[DatabaseHelper] = None


def get_db() -> DatabaseHelper:
    """
    获取全局数据库实例（单例模式）

    整个应用生命周期内共享同一个 DatabaseHelper 实例，
    首次调用时自动初始化表结构。

    Returns:
        DatabaseHelper 全局唯一实例
    """
    global _db_instance
    if _db_instance is None:
        _db_instance = DatabaseHelper()
        _db_instance.initialize_database()
    return _db_instance
