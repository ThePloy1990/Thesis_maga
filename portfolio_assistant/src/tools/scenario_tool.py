import uuid
import copy
from typing import Dict

# Импортируем из вашей обертки, которая теперь будет в pf_agents
from pf_agents import function_tool 

from src.market_snapshot.registry import SnapshotRegistry
from src.market_snapshot.model import MarketSnapshot # MarketSnapshot тоже нужен для type hinting и работы

# Определение расположения S3 стаба и Redis (можно вынести в конфиг, но пока оставим как в test_snapshot)
# Эти значения могут быть не нужны здесь, если SnapshotRegistry их сам знает из своей конфигурации
# TEST_S3_STUB_PATH = "local_test/snapshots_scenario_tool" 
# REDIS_HOST = "localhost"
# REDIS_PORT = 6379


@function_tool
def scenario_adjust_tool(snapshot_id: str, deltas: Dict[str, float]) -> str:
    """
    Adjusts the expected returns (mu) of a given market snapshot based on provided deltas
    and saves it as a new scenario snapshot.

    Args:
        snapshot_id: The ID of the base market snapshot to adjust.
        deltas: A dictionary where keys are ticker symbols (str) and values are the
                adjustments (float) to be added to the respective mu values.
                Example: {"AAPL": 0.01, "GOOG": -0.005}

    Returns:
        The ID of the newly created and saved scenario market snapshot.
    """
    # Инициализируем SnapshotRegistry. 
    # Предполагается, что SnapshotRegistry сконфигурирован глобально или его конструктор знает, где брать Redis/S3.
    # Если SnapshotRegistry требует явных параметров здесь, их нужно будет передать.
    # Основываясь на предыдущей структуре registry = SnapshotRegistry(redis_host=REDIS_HOST, redis_port=REDIS_PORT, s3_stub_path=TEST_S3_STUB_PATH)
    # но лучше, если SnapshotRegistry будет self-configurable или синглтоном.
    # Для простоты, пока будем считать, что он сам знает свои настройки по умолчанию (localhost redis, определенный s3_stub)
    
    # Используем путь к S3 стабу по аналогии с другими тестами/инструментами
    # Это лучше вынести в конфигурацию, но для примера пусть будет здесь, если понадобится явно
    s3_stub_path = "local/snapshots_scenario" # Отдельный путь для сценариев
    registry = SnapshotRegistry(s3_stub_path=s3_stub_path) # Предполагаем, что Redis по умолчанию localhost:6379

    original_snapshot: MarketSnapshot = registry.load(snapshot_id)
    if not original_snapshot:
        # Можно добавить обработку ошибок, если снэпшот не найден
        raise ValueError(f"Original snapshot with id '{snapshot_id}' not found.")

    # Глубокое копирование, чтобы не изменять оригинальный снэпшот в памяти
    scenario_snapshot = copy.deepcopy(original_snapshot)

    # Применяем дельты к mu
    for ticker, delta_value in deltas.items():
        if ticker in scenario_snapshot.mu:
            scenario_snapshot.mu[ticker] += delta_value
        else:
            # Обработка случая, если тикер из deltas отсутствует в снэпшоте
            # Можно логировать предупреждение или вызывать ошибку, или добавлять тикер с дельтой как mu
            print(f"Warning: Ticker '{ticker}' from deltas not found in snapshot.mu. Ignoring delta for this ticker.")
            # scenario_snapshot.mu[ticker] = delta_value # Или так, если хотим добавить

    # Генерируем новый ID для scenario_snapshot
    suffix = f"-scn-{uuid.uuid4().hex[:4]}"
    new_id = original_snapshot.meta.id + suffix
    scenario_snapshot.meta.id = new_id
    
    # Обновляем время создания (опционально, но логично для нового объекта)
    # scenario_snapshot.meta.created_at = datetime.now(timezone.utc) # Если нужно

    # Сохраняем новый снэпшот
    saved_snapshot_id = registry.save(scenario_snapshot)
    
    # Убедимся, что сохраненный ID совпадает с тем, что мы сгенерировали (registry.save может его изменить, если уже существует)
    # В нашей текущей реализации registry.save использует snapshot.meta.id если он есть.
    if saved_snapshot_id != new_id:
         # Это может случиться, если ID каким-то образом изменился при сохранении.
         # Логируем или обрабатываем, если это не ожидаемое поведение.
         print(f"Warning: Saved snapshot ID '{saved_snapshot_id}' differs from generated ID '{new_id}'. Using saved ID.")
         return saved_snapshot_id
         
    return new_id 