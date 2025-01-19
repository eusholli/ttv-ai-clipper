#!/usr/bin/env python3
import psycopg2
import os
from dotenv import load_dotenv

def get_db_connection(env_file):
    """Create and return a database connection using specified env file"""
    load_dotenv(env_file)
    
    conn = psycopg2.connect(
        dbname=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PWD'),
        host=os.getenv('DB_HOST'),
        sslmode='require',
        connect_timeout=30
    )
    return conn

def get_schema_info(cursor):
    """Get complete schema information including tables, columns, indexes, and extensions"""
    schema_info = {
        'tables': {},
        'indexes': {},
        'extensions': set()
    }
    
    # Get installed extensions
    cursor.execute("""
        SELECT extname FROM pg_extension;
    """)
    schema_info['extensions'] = {row[0] for row in cursor.fetchall()}
    
    # Get table definitions
    cursor.execute("""
        SELECT 
            t.tablename,
            array_agg(
                format('%s %s %s',
                    a.attname,
                    pg_catalog.format_type(a.atttypid, a.atttypmod),
                    CASE WHEN a.attnotnull THEN 'NOT NULL' ELSE '' END
                ) ORDER BY a.attnum
            ) as columns
        FROM pg_catalog.pg_tables t
        JOIN pg_catalog.pg_class c ON t.tablename = c.relname
        JOIN pg_catalog.pg_attribute a ON c.oid = a.attrelid
        WHERE t.schemaname = 'public'
        AND a.attnum > 0
        AND NOT a.attisdropped
        GROUP BY t.tablename;
    """)
    for table, columns in cursor.fetchall():
        schema_info['tables'][table] = columns
    
    # Get index definitions
    cursor.execute("""
        SELECT 
            schemaname,
            tablename,
            indexname,
            indexdef
        FROM pg_indexes
        WHERE schemaname = 'public';
    """)
    for schema, table, index_name, index_def in cursor.fetchall():
        schema_info['indexes'][index_name] = {
            'table': table,
            'definition': index_def
        }
    
    return schema_info

def generate_migration_sql(source_schema, target_schema):
    """Generate SQL to migrate from source to target schema"""
    migration_sql = []
    
    # Extensions
    for ext in target_schema['extensions'] - source_schema['extensions']:
        migration_sql.append(f"CREATE EXTENSION IF NOT EXISTS {ext};")
    
    # Tables and columns
    for table, target_columns in target_schema['tables'].items():
        if table not in source_schema['tables']:
            # Create missing table
            columns_sql = ",\n    ".join(target_columns)
            migration_sql.append(f"""
CREATE TABLE IF NOT EXISTS {table} (
    {columns_sql}
);""")
        else:
            # Compare columns and add missing ones
            source_cols = set(source_schema['tables'][table])
            target_cols = set(target_columns)
            missing_cols = target_cols - source_cols
            
            for col in missing_cols:
                col_name = col.split()[0]
                col_def = ' '.join(col.split()[1:])
                migration_sql.append(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col_name} {col_def};")
    
    # Indexes
    for index_name, index_info in target_schema['indexes'].items():
        if index_name not in source_schema['indexes']:
            migration_sql.append(index_info['definition'])
    
    return '\n\n'.join(migration_sql)

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Connect to both databases
    source_conn = get_db_connection(os.path.join(script_dir, '.env'))
    target_conn = get_db_connection(os.path.join(script_dir, '.env.production'))
    
    try:
        # Get schema info from both databases
        with source_conn.cursor() as source_cur:
            source_schema = get_schema_info(source_cur)
            print("\nSource Schema (.env):")
            print("Extensions:", source_schema['extensions'])
            print("\nTables and Columns:")
            for table, columns in source_schema['tables'].items():
                print(f"\n{table}:")
                for col in columns:
                    print(f"  {col}")
            print("\nIndexes:", source_schema['indexes'].keys())
        
        with target_conn.cursor() as target_cur:
            target_schema = get_schema_info(target_cur)
            print("\nTarget Schema (.env.production):")
            print("Extensions:", target_schema['extensions'])
            print("\nTables and Columns:")
            for table, columns in target_schema['tables'].items():
                print(f"\n{table}:")
                for col in columns:
                    print(f"  {col}")
            print("\nIndexes:", target_schema['indexes'].keys())
            
            # Compare column definitions
            print("\nComparing column definitions:")
            for table in source_schema['tables'].keys() & target_schema['tables'].keys():
                source_cols = set(source_schema['tables'][table])
                target_cols = set(target_schema['tables'][table])
                
                if source_cols != target_cols:
                    print(f"\nDifferences in table {table}:")
                    print("Columns only in source:", source_cols - target_cols)
                    print("Columns only in target:", target_cols - source_cols)
        
        # Generate migration SQL
        migration_sql = generate_migration_sql(source_schema, target_schema)
        
        # Write migration SQL to file
        migration_file = os.path.join(script_dir, 'migrations', '003_sync_database_schema.sql')
        os.makedirs(os.path.dirname(migration_file), exist_ok=True)
        
        if migration_sql.strip():
            with open(migration_file, 'w') as f:
                f.write(migration_sql)
            print(f"\nMigration SQL has been written to {migration_file}")
            print("\nGenerated SQL:")
            print(migration_sql)
        else:
            print("\nNo schema differences found - no migration SQL generated")
        
    finally:
        source_conn.close()
        target_conn.close()

if __name__ == "__main__":
    main()
