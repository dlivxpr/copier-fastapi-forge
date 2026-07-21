# 同等支持 SQLAlchemy 与 SQLModel

启用 PostgreSQL 时提供 `sqlalchemy | sqlmodel` 两种 ORM 选择并对两条生成路径进行同等验证，默认使用 SQLAlchemy；未启用数据库时不询问 ORM。两条路径都生成一个部署级共享的示例 CRUD 资源，完整覆盖 model、migration、repository、service、API 和测试，使持久化分层具备可运行的纵向验收载体。该选择保留不同建模风格的组合灵活性，代价是数据库分支必须持续同等验证，不能把 SQLModel 降为未经完整验证的示例路径。
