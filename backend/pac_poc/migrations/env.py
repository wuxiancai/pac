from alembic import context


config = context.config
connection = config.attributes.get("connection")
if connection is None:
    raise RuntimeError("application migrations require a keyed SQLCipher connection")

context.configure(connection=connection, render_as_batch=False)
with context.begin_transaction():
    context.run_migrations()
