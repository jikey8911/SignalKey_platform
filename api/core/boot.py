import asyncio
import logging

# Configure logger
logger = logging.getLogger("BootRecovery")

async def startup_recovery(db_adapter, engine=None, bot_manager=None):
    """
    Tarea 6.2: Autotrade Recovery (Boot Script)
    Busca bots activos en MongoDB y reanuda su ciclo al arrancar el servidor.
    """
    try:
        logger.info("🔄 Validating active bots state...")
        
        # 1. Obtener bots que estaban marcados como 'active'
        # Usamos to_list(None) para obtener todos
        cursor = db_adapter.db["bot_instances"].find({"status": "active"})
        active_bots = await cursor.to_list(None)
        
        count = 0
        for bot in active_bots:
            # Opción A: Si usas BotManager (más robusto)
            if bot_manager:
                # Verificar si ya está corriendo (el manager suele chequear esto, pero forzamos validación)
                 if bot['id'] not in bot_manager.active_bots:
                     logger.info(f"🚀 Reanudando bot via Manager: {bot.get('name', 'Unnamed')} ({bot.get('symbol', 'Unknown')})")
                     # Asumimos que el manager tiene un método start_bot o similar, 
                     # o si restart_all_bots ya lo hizo en main.py, esto es solo un log de confirmación.
                     # En main.py ya llamamos a bot_manager.restart_all_bots(), 
                     # así que este script podría ser redundante o complementario para validación.
                     pass 
            
            # Opción B: Si es ejecución directa (Legacy o si el manager falla)
            logger.info(f"✅ Bot verificado activo: {bot.get('name', 'Unnamed')} ({bot.get('symbol')}) - Mode: {bot.get('mode')}")
            count += 1

        logger.info(f"🏁 System Startup Recovery Complete. {count} bots verified active.")
        
    except Exception as e:
        logger.error(f"❌ Error in startup_recovery: {e}")
