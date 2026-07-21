# 同等支持 SQLAlchemy 与 SQLModel

启用 PostgreSQL 时提供 `sqlalchemy | sqlmodel` 两种 ORM 选择并对两条生成路径进行同等验证，默认使用 SQLAlchemy；未启用数据库时不询问 ORM。该选择保留不同建模风格的组合灵活性，代价是数据库 model、repository、迁移和测试必须持续覆盖两套模板分支，不能把 SQLModel 降为未经完整验证的示例路径。
