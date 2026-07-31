import os
from urllib.parse import urlparse
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import pymysql

app = Flask(__name__)
# Permitir peticiones AJAX desde orígenes cruzados (CORS) para desarrollo
CORS(app)

def obtener_conexion():
    """Abre una conexión usando las variables inyectadas por Clever Cloud."""
    database_url = os.environ.get("DATABASE_URL")

    if database_url:
        # Útil para desarrollo local o proveedores que entregan una URL completa.
        parsed = urlparse(database_url)
        config = {
            "host": parsed.hostname,
            "port": parsed.port or 3306,
            "user": parsed.username,
            "password": parsed.password or "",
            "database": parsed.path.lstrip("/"),
        }
    else:
        # Estas variables aparecen automáticamente al vincular un add-on MySQL
        # a la aplicación en Clever Cloud.
        required = ("MYSQL_ADDON_HOST", "MYSQL_ADDON_USER", "MYSQL_ADDON_DB")
        missing = [name for name in required if not os.environ.get(name)]
        if missing:
            raise RuntimeError(
                "Faltan variables de conexión MySQL: " + ", ".join(missing)
            )
        config = {
            "host": os.environ["MYSQL_ADDON_HOST"],
            "port": int(os.environ.get("MYSQL_ADDON_PORT", "3306")),
            "user": os.environ["MYSQL_ADDON_USER"],
            "password": os.environ.get("MYSQL_ADDON_PASSWORD", ""),
            "database": os.environ["MYSQL_ADDON_DB"],
        }

    return pymysql.connect(
        **config,
        cursorclass=pymysql.cursors.DictCursor,
        charset="utf8mb4",
    )

# Ruta principal: Renderiza la interfaz web (frontend)
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/health')
def health():
    """Endpoint ligero para el health check de Clever Cloud."""
    return jsonify({"status": "ok"})


# ==========================================
# API ENDPOINTS (COMUNICACIÓN JSON CON AJAX)
# ==========================================

# 1. GET - Listar empleados con paginación integrada en MySQL
@app.route('/api/empleados', methods=['GET'])
def listar_empleados():
    try:
        # Obtener parámetros de búsqueda y paginación desde el AJAX GET request
        buscar = request.args.get('buscar', default='', type=str)
        puesto_filtro = request.args.get('puesto', default='todos', type=str)
        page = request.args.get('page', default=1, type=int)
        limit = request.args.get('limit', default=5, type=int)
        
        offset = (page - 1) * limit
        
        conexion = obtener_conexion()
        with conexion.cursor() as cursor:
            # Construcción dinámica de la consulta SQL para filtros
            query_where = "WHERE 1=1"
            params = []
            
            if buscar:
                query_where += " AND (nombre LIKE %s OR correo LIKE %s OR telefono LIKE %s OR puesto LIKE %s)"
                search_val = f"%{buscar}%"
                params.extend([search_val, search_val, search_val, search_val])
                
            if puesto_filtro and puesto_filtro != 'todos':
                query_where += " AND puesto = %s"
                params.append(puesto_filtro)
                
            # 1. Obtener conteo total de registros filtrados (para la paginación de jQuery)
            count_sql = f"SELECT COUNT(*) as total FROM empleados {query_where}"
            cursor.execute(count_sql, params)
            total_records = cursor.fetchone()['total']
            
            # 2. Obtener los empleados paginados (Nota el %% duplicado para escapar el formato de Python)
            select_sql = f"""
                SELECT id, nombre, telefono, correo, puesto, 
                       DATE_FORMAT(fecha_creacion, '%%Y-%%m-%%dT%%H:%%i:%%s.000Z') as fechaCreacion 
                FROM empleados 
                {query_where} 
                ORDER BY fecha_creacion DESC 
                LIMIT %s OFFSET %s
            """
            cursor.execute(select_sql, params + [limit, offset])
            empleados = cursor.fetchall()
            
            # 3. Obtener lista de puestos únicos para el selector de filtros
            cursor.execute("SELECT DISTINCT puesto FROM empleados WHERE puesto IS NOT NULL AND puesto != ''")
            puestos_unicos = [row['puesto'] for row in cursor.fetchall()]
            
        conexion.close()
        
        # Responder con la estructura JSON esperada por el plugin de jQuery
        return jsonify({
            "status": "success",
            "page": page,
            "limit": limit,
            "total_records": total_records,
            "total_pages": (total_records + limit - 1) // limit,
            "puestos_unicos": puestos_unicos,
            "data": empleados
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": f"Error de servidor: {str(e)}"}), 500


# 2. GET - Obtener un único empleado por ID
@app.route('/api/empleados/<int:empleado_id>', methods=['GET'])
def obtener_empleado(empleado_id):
    try:
        conexion = obtener_conexion()
        with conexion.cursor() as cursor:
            sql = "SELECT id, nombre, telefono, correo, puesto FROM empleados WHERE id = %s"
            cursor.execute(sql, (empleado_id,))
            empleado = cursor.fetchone()
        conexion.close()
        
        if not empleado:
            return jsonify({"status": "error", "message": "Empleado no encontrado"}), 404
            
        return jsonify({"status": "success", "data": empleado})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# 3. POST - Crear un nuevo empleado
@app.route('/api/empleados', methods=['POST'])
def crear_empleado():
    try:
        datos = request.get_json()
        
        nombre = datos.get('nombre', '').strip()
        telefono = datos.get('telefono', '').strip()
        correo = datos.get('correo', '').strip().lower()
        puesto = datos.get('puesto', '').strip()
        
        if not nombre or not telefono or not correo or not puesto:
            return jsonify({"status": "error", "message": "Todos los campos son obligatorios."}), 400
            
        conexion = obtener_conexion()
        with conexion.cursor() as cursor:
            # Validar correo único
            cursor.execute("SELECT id FROM empleados WHERE correo = %s", (correo,))
            if cursor.fetchone():
                conexion.close()
                return jsonify({"status": "error", "message": "Ya existe un empleado con este correo electrónico."}), 400
                
            # Insertar registro
            sql = "INSERT INTO empleados (nombre, telefono, correo, puesto) VALUES (%s, %s, %s, %s)"
            cursor.execute(sql, (nombre, telefono, correo, puesto))
            nuevo_id = cursor.lastrowid
            conexion.commit()
            
            # Obtener el registro creado para responder con él
            cursor.execute("SELECT id, nombre, telefono, correo, puesto, fecha_creacion as fechaCreacion FROM empleados WHERE id = %s", (nuevo_id,))
            nuevo_empleado = cursor.fetchone()
            
        conexion.close()
        return jsonify({"status": "success", "message": "Empleado creado exitosamente", "data": nuevo_empleado}), 201
        
    except Exception as e:
        return jsonify({"status": "error", "message": f"Error al insertar: {str(e)}"}), 500


# 4. PUT - Actualizar un empleado existente
@app.route('/api/empleados/<int:empleado_id>', methods=['PUT'])
def actualizar_empleado(empleado_id):
    try:
        datos = request.get_json()
        
        nombre = datos.get('nombre', '').strip()
        telefono = datos.get('telefono', '').strip()
        correo = datos.get('correo', '').strip().lower()
        puesto = datos.get('puesto', '').strip()
        
        if not nombre or not telefono or not correo or not puesto:
            return jsonify({"status": "error", "message": "Todos los campos son obligatorios."}), 400
            
        conexion = obtener_conexion()
        with conexion.cursor() as cursor:
            # Verificar si existe el empleado
            cursor.execute("SELECT id FROM empleados WHERE id = %s", (empleado_id,))
            if not cursor.fetchone():
                conexion.close()
                return jsonify({"status": "error", "message": "El empleado que intentas modificar no existe."}), 404
                
            # Verificar correo único en otros empleados
            cursor.execute("SELECT id FROM empleados WHERE correo = %s AND id != %s", (correo, empleado_id))
            if cursor.fetchone():
                conexion.close()
                return jsonify({"status": "error", "message": "El correo electrónico ya está registrado en otro empleado."}), 400
                
            # Actualizar datos
            sql = "UPDATE empleados SET nombre=%s, telefono=%s, correo=%s, puesto=%s WHERE id=%s"
            cursor.execute(sql, (nombre, telefono, correo, puesto, empleado_id))
            conexion.commit()
            
            # Obtener el registro actualizado
            cursor.execute("SELECT id, nombre, telefono, correo, puesto, fecha_creacion as fechaCreacion FROM empleados WHERE id = %s", (empleado_id,))
            empleado_actualizado = cursor.fetchone()
            
        conexion.close()
        return jsonify({"status": "success", "message": "Empleado actualizado exitosamente", "data": empleado_actualizado})
        
    except Exception as e:
        return jsonify({"status": "error", "message": f"Error al actualizar: {str(e)}"}), 500


# 5. DELETE - Eliminar un empleado
@app.route('/api/empleados/<int:empleado_id>', methods=['DELETE'])
def eliminar_empleado(empleado_id):
    try:
        conexion = obtener_conexion()
        with conexion.cursor() as cursor:
            # Verificar si existe
            cursor.execute("SELECT id, nombre FROM empleados WHERE id = %s", (empleado_id,))
            empleado = cursor.fetchone()
            if not empleado:
                conexion.close()
                return jsonify({"status": "error", "message": "El empleado no existe."}), 404
                
            # Eliminar
            cursor.execute("DELETE FROM empleados WHERE id = %s", (empleado_id,))
            conexion.commit()
            
        conexion.close()
        return jsonify({"status": "success", "message": f"Empleado '{empleado['nombre']}' eliminado correctamente.", "id": empleado_id})
        
    except Exception as e:
        return jsonify({"status": "error", "message": f"Error al eliminar: {str(e)}"}), 500


if __name__ == '__main__':
    # Ejecución local o en Clever Cloud.
    # Clever Cloud expone el puerto en la variable de entorno PORT.
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() in ('1', 'true', 'yes')
    print(f"Iniciando servidor Flask en 0.0.0.0:{port} (debug={debug})")
    app.run(host='0.0.0.0', port=port, debug=debug)
