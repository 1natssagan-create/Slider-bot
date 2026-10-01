import asyncio
import datetime
import logging
import os
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    ForeignKey,
    Integer,
    String,
    create_engine,
    desc,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

# Берем токен из настроек сервера
TOKEN = os.getenv("BOT_TOKEN")

# База данных сохраняется в локальный файл
DB_PATH = "slider_bot.db"

Base = declarative_base()
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
SessionLocal = sessionmaker(bind=engine)


class User(Base):
  __tablename__ = "users"
  telegram_id = Column(BigInteger, primary_key=True)
  current_split_index = Column(Integer, default=0)
  logs = relationship("DailyLog", back_populates="user")


class DailyLog(Base):
  __tablename__ = "daily_logs"
  id = Column(Integer, primary_key=True, autoincrement=True)
  user_id = Column(BigInteger, ForeignKey("users.telegram_id"))
  date = Column(Date, default=datetime.date.today)
  sleep_score = Column(Integer)
  stress_score = Column(Integer)
  doms_score = Column(Integer)
  energy_score = Column(Integer)
  total_score = Column(Integer)
  zone = Column(String)
  group_name = Column(String)
  water_done = Column(Boolean, default=False)
  workout_done = Column(Boolean, default=False)
  nutrition_done = Column(Boolean, default=False)
  user = relationship("User", back_populates="logs")


Base.metadata.create_all(engine)

ROTATION_CYCLE = [
    {"id": 0, "name": "Ноги / Ягодицы"},
    {"id": 1, "name": "Спина"},
    {"id": 2, "name": "Пресс / Кор"},
    {"id": 3, "name": "Ягодицы (акцент) / Ноги"},
]

EXERCISES = {
    0: [
        "Приседания (или Гакк/Жим ногами)",
        "Румынская тяга с гантелями",
        "Выпады назад",
        "Сгибания ног в тренажере",
        "Подъемы на носки",
    ],
    1: [
        "Тяга верхнего блока / Подтягивания",
        "Тяга гантели/штанги в наклоне",
        "Тяга горизонтального блока к поясу",
        "Пулловер на блоке / с гантелью",
        "Гиперэкстензия",
    ],
    2: [
        "Скручивания на фитболе / коврике",
        "Подъемы ног в висе / упоре",
        "Планка (с удержанием)",
        "«Melted / Вакуум» или боковая планка",
        "Молитва на блоке / Книжка",
    ],
    3: [
        "Ягодичный мост со штангой/гантелью",
        "Румынская тяга на одной ноге",
        "Отведение ноги назад в кроссовере/с резинкой",
        "Боковые выпады / Реверанс",
        "Гиперэкстензия с акцентом на ягодицы",
    ],
}


class SurveyFSM(StatesGroup):
  sleep = State()
  stress = State()
  doms = State()
  energy = State()


def get_survey_keyboard():
  buttons = [
      [
          InlineKeyboardButton(text=str(i), callback_data=f"score_{i}")
          for i in range(1, 6)
      ]
  ]
  return InlineKeyboardMarkup(inline_keyboard=buttons)


router = Router()


async def start_morning_survey(bot: Bot, chat_id: int, user_id: int, state: FSMContext):
  session = SessionLocal()
  user = session.query(User).filter_by(telegram_id=user_id).first()
  if not user:
    user = User(telegram_id=user_id, current_split_index=0)
    session.add(user)
    session.commit()
  session.close()

  await bot.send_message(
      chat_id,
      "☀️ **Доброе утро! Пора пройти утреннюю оценку готовности (RSI).**\n\n1/4."
      " **Сон**: Качество и продолжительность сна (1 — плохо/мало, 5 —"
      " отлично):",
      reply_markup=get_survey_keyboard(),
      parse_mode="Markdown",
  )
  await state.set_state(SurveyFSM.sleep)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
  await start_morning_survey(bot, message.chat.id, message.from_user.id, state)


@router.callback_query(SurveyFSM.sleep, F.data.startswith("score_"))
async def process_sleep(callback: CallbackQuery, state: FSMContext):
  await state.update_data(sleep=int(callback.data.split("_")[1]))
  await callback.message.edit_text(
      "2/4. **Стресс**: Уровень бытового/рабочего стресса (1 — сильный аврал, 5"
      " — спокойный день):",
      reply_markup=get_survey_keyboard(),
  )
  await state.set_state(SurveyFSM.stress)


@router.callback_query(SurveyFSM.stress, F.data.startswith("score_"))
async def process_stress(callback: CallbackQuery, state: FSMContext):
  await state.update_data(stress=int(callback.data.split("_")[1]))
  await callback.message.edit_text(
      "3/4. **Боль (DOMS)**: Мышечная боль / восстановление (1 — сильная боль, 5"
      " — полное отсутствие):",
      reply_markup=get_survey_keyboard(),
  )
  await state.set_state(SurveyFSM.doms)


@router.callback_query(SurveyFSM.doms, F.data.startswith("score_"))
async def process_doms(callback: CallbackQuery, state: FSMContext):
  await state.update_data(doms=int(callback.data.split("_")[1]))
  await callback.message.edit_text(
      "4/4. **Энергия**: Мотивация и запас сил (1 — истощен, 5 — полон сил):",
      reply_markup=get_survey_keyboard(),
  )
  await state.set_state(SurveyFSM.energy)


@router.callback_query(SurveyFSM.energy, F.data.startswith("score_"))
async def process_energy(callback: CallbackQuery, state: FSMContext):
  data = await state.get_data()
  energy_score = int(callback.data.split("_")[1])
  total = data["sleep"] + data["stress"] + data["doms"] + energy_score
  doms_score = data["doms"]

  session = SessionLocal()
  user = session.query(User).filter_by(telegram_id=callback.from_user.id).first()

  zone = (
      "Красная" if total <= 9 else ("Жёлтая" if total <= 15 else "Зелёная")
  )
  split_idx = user.current_split_index
  shifted = False

  if doms_score <= 2 and zone != "Красная":
    split_idx = (split_idx + 1) % len(ROTATION_CYCLE)
    shifted = True

  group_info = ROTATION_CYCLE[split_idx]

  daily_log = DailyLog(
      user_id=user.telegram_id,
      date=datetime.date.today(),
      sleep_score=data["sleep"],
      stress_score=data["stress"],
      doms_score=doms_score,
      energy_score=energy_score,
      total_score=total,
      zone=zone,
      group_name=group_info["name"],
  )
  session.add(daily_log)

  if zone != "Красная":
    user.current_split_index = (split_idx + 1) % len(ROTATION_CYCLE)

  session.commit()
  session.close()

  await state.clear()
  await callback.message.delete()
  await send_checklist(
      callback.message.chat.id,
      callback.from_user.id,
      total,
      zone,
      group_info["id"],
      group_info["name"],
      shifted,
  )


async def send_checklist(
    chat_id, user_id, total, zone, group_id, group_name, shifted=False
):
  session = SessionLocal()
  log = (
      session.query(DailyLog)
      .filter_by(user_id=user_id, date=datetime.date.today())
      .first()
  )

  if zone == "Красная":
    emoji, mode_text, sets_count = (
        "🔴",
        "МФР / Заминка / Прогулка (30 мин лёгкого движения)",
        0,
    )
  elif zone == "Жёлтая":
    emoji, mode_text, sets_count = (
        "🟡",
        "Адаптивная силовая (-1 подход, RIR 2–3)",
        2,
    )
  else:
    emoji, mode_text, sets_count = (
        "🟢",
        "Пиковая силовая (100% планового объема)",
        3,
    )

  text = f"{emoji} **Зона:** {zone.upper()} ({total} баллов)\n"
  text += f"**Режим:** {mode_text}\n"
  if shifted:
    text += (
        "⚠️ *Сработало правило защиты от травм: группа сдвинута из-за боли в"
        " мышцах.*\n"
    )
  text += f"**Группа дня:** {group_name}\n\n📋 **Твой план на сегодня:**\n"

  w_check = "✅" if log.water_done else "▫️"
  tr_check = "✅" if log.workout_done else "▫️"
  f_check = "✅" if log.nutrition_done else "▫️"

  text += f"{w_check} **Вода:** 2–2.5 литра\n"
  text += (
      f"{f_check} **Питание:** "
      + (
          "Восстановление, гидратация"
          if zone == "Красная"
          else "Базовый рацион"
      )
      + "\n"
  )

  if zone != "Красная":
    text += f"{tr_check} **Тренировка ({group_name}):**\n"
    for ex in EXERCISES[group_id]:
      text += f"   • {ex} ({sets_count} подх.)\n"
  else:
    text += f"{tr_check} **Восстановление:** МФР/Прогулка 30 мин\n"

  kb = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text=f"{'✅' if log.water_done else '💧'} Вода",
                  callback_data="toggle_water",
              )
          ],
          [
              InlineKeyboardButton(
                  text=(
                      f"{'✅' if log.workout_done else '🏋️'} Тренировка"
                      " выполнена"
                  ),
                  callback_data="toggle_workout",
              )
          ],
          [
              InlineKeyboardButton(
                  text=f"{'✅' if log.nutrition_done else '🥗'} Питание ок",
                  callback_data="toggle_nutrition",
              )
          ],
          [
              InlineKeyboardButton(
                  text="📊 Моя статистика", callback_data="show_stats"
              )
          ],
      ]
  )

  await bot.send_message(chat_id, text, reply_markup=kb, parse_mode="Markdown")
  session.close()


@router.callback_query(F.data.startswith("toggle_"))
async def toggle_checklist(callback: CallbackQuery):
  action = callback.data.split("_")[1]
  session = SessionLocal()
  log = (
      session.query(DailyLog)
      .filter_by(user_id=callback.from_user.id, date=datetime.date.today())
      .first()
  )

  if log:
    if action == "water":
      log.water_done = not log.water_done
    elif action == "workout":
      log.workout_done = not log.workout_done
    elif action == "nutrition":
      log.nutrition_done = not log.nutrition_done
    session.commit()

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{'✅' if log.water_done else '💧'} Вода",
                    callback_data="toggle_water",
                )
            ],
            [
                InlineKeyboardButton(
                    text=(
                        f"{'✅' if log.workout_done else '🏋️'} Тренировка"
                        " выполнена"
                    ),
                    callback_data="toggle_workout",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"{'✅' if log.nutrition_done else '🥗'} Питание ок",
                    callback_data="toggle_nutrition",
                )
            ],
            [
                InlineKeyboardButton(
                    text="📊 Моя статистика", callback_data="show_stats"
                )
            ],
        ]
    )
    await callback.message.edit_reply_markup(reply_markup=kb)
    await callback.answer("Статус обновлен!")
  session.close()


@router.callback_query(F.data == "show_stats")
async def callback_show_stats(callback: CallbackQuery):
  session = SessionLocal()
  logs = (
      session.query(DailyLog)
      .filter(
          DailyLog.user_id == callback.from_user.id,
          DailyLog.date
          >= (datetime.date.today() - datetime.timedelta(days=7)),
      )
      .order_by(desc(DailyLog.date))
      .limit(7)
      .all()
  )
  session.close()

  if not logs:
    await callback.answer("История пока пуста!", show_alert=True)
    return

  text = "📊 **Статистика за 7 дней:**\n\n"
  for l in logs:
    z_emoji = {"Красная": "🔴", "Жёлтая": "🟡", "Зелёная": "🟢"}.get(
        l.zone, "⚪"
    )
    text += (
        f"📅 **{l.date.strftime('%d.%m')}** — {z_emoji} **{l.total_score}"
        f" б.**\n└ 💧{'✅' if l.water_done else '❌'} |"
        f" 🏋️{'✅' if l.workout_done else '❌'} |"
        f" 🥗{'✅' if l.nutrition_done else '❌'}\n"
    )

  kb = InlineKeyboardMarkup(
      inline_keyboard=[
          [InlineKeyboardButton(text="◀️ Закрыть", callback_data="close_stats")]
      ]
  )
  await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")
  await callback.answer()


@router.callback_query(F.data == "close_stats")
async def close_stats(callback: CallbackQuery):
  await callback.message.delete()


bot = Bot(token=TOKEN)
dp = Dispatcher()
dp.include_router(router)


async def main():
  scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

  async def morning_job():
    session = SessionLocal()
    for u in session.query(User).all():
      fsm = dp.fsm.get_context(bot, u.telegram_id, u.telegram_id)
      await start_morning_survey(bot, u.telegram_id, u.telegram_id, fsm)
    session.close()

  scheduler.add_job(
      morning_job,
      trigger=CronTrigger(hour=8, minute=0),
      id="morning_survey",
      replace_existing=True,
  )
  scheduler.start()

  logging.info("Бот запущен!")
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())
  
