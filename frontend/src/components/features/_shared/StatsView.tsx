import React, { useEffect, useState } from "react";
import { Button } from "@/components/ui";
import { statsApi, type StatsBreakdown } from "@/services/api";
import styles from "./StatsView.module.css";

export interface StatsViewProps {
  /** "overall" — сводка по всем режимам; иначе — конкретный режим */
  mode: "overall" | "quiz" | "sobes" | "design" | "chat";
  onBack: () => void;
  /** Заголовок режима (для подзаголовка) */
  title?: string;
}

const MODE_LABELS: Record<string, string> = {
  overall: "Все режимы",
  quiz: "Тестирование",
  sobes: "Собеседование",
  design: "Системный дизайн",
  chat: "Интервью",
};

export const StatsView: React.FC<StatsViewProps> = ({ mode, onBack, title }) => {
  const [overview, setOverview] = useState<Record<string, StatsBreakdown> | null>(null);
  const [me, setMe] = useState<{ display_name: string; username: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    Promise.all([statsApi.overview(), statsApi.me()])
      .then(([ov, m]) => {
        if (cancelled) return;
        setOverview(ov.features);
        setMe(m);
      })
      .catch((err: Error) => {
        if (cancelled) return;
        if (err.message.includes("400")) {
          setError("Не задано имя пользователя. Вернитесь на главную и представьтесь.");
        } else if (err.message.includes("503")) {
          setError("PostgreSQL недоступна. Перезапустите docker compose.");
        } else {
          setError(err.message);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const heading = title ?? MODE_LABELS[mode] ?? "Статистика";

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <Button variant="secondary" onClick={onBack}>
          ← Назад
        </Button>
        <h1 className={styles.title}>📊 Статистика ответов — {heading}</h1>
      </header>

      {me && (
        <p className={styles.userLine}>
          Пользователь: <strong>{me.display_name}</strong>
        </p>
      )}

      {loading && <p className={styles.loading}>Загружаем статистику…</p>}

      {error && (
        <div className={styles.error}>
          <p>⚠️ {error}</p>
        </div>
      )}

      {overview && !loading && !error && (
        <>
          {mode === "overall" ? (
            <div className={styles.grid}>
              {(["quiz", "sobes", "design", "chat"] as const).map((feat) => {
                const bd = overview[feat];
                return (
                  <ModeCard key={feat} feature={feat} breakdown={bd} />
                );
              })}
            </div>
          ) : (
            <SingleFeatureView feature={mode} breakdown={overview[mode]} />
          )}
        </>
      )}
    </div>
  );
};

const MODE_TITLES: Record<string, string> = {
  quiz: "Тестирование",
  sobes: "Собеседование",
  design: "Системный дизайн",
  chat: "Интервью",
};

const ModeCard: React.FC<{ feature: string; breakdown: StatsBreakdown }> = ({ feature, breakdown }) => {
  const total = breakdown.total;
  return (
    <div className={styles.card}>
      <h3 className={styles.cardTitle}>{MODE_TITLES[feature] ?? feature}</h3>
      <div className={styles.metrics}>
        <Metric label="Всего" value={total} />
        <Metric label="Правильно" value={breakdown.correct} kind="correct" />
        <Metric label="Частично" value={breakdown.partial} kind="partial" />
        <Metric label="Неправильно" value={breakdown.incorrect} kind="incorrect" />
      </div>
      {total > 0 ? (
        <div className={styles.accuracy}>
          <div className={styles.accuracyBar}>
            <div className={styles.barCorrect} style={{ width: `${(breakdown.correct / total) * 100}%` }} />
            <div className={styles.barPartial} style={{ width: `${(breakdown.partial / total) * 100}%` }} />
            <div className={styles.barIncorrect} style={{ width: `${(breakdown.incorrect / total) * 100}%` }} />
          </div>
          <p className={styles.accuracyText}>
            Точность: <strong>{breakdown.accuracy_percent.toFixed(1)}%</strong>
          </p>
        </div>
      ) : (
        <p className={styles.emptyText}>Пока нет данных. Пройдите, пожалуйста, этот режим.</p>
      )}
    </div>
  );
};

const SingleFeatureView: React.FC<{ feature: string; breakdown: StatsBreakdown }> = ({ feature, breakdown }) => {
  const [filter, setFilter] = useState<"all" | "incorrect" | "partial">("incorrect");
  const [answers, setAnswers] = useState<unknown[]>([]);
  const [loadingAnswers, setLoadingAnswers] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (feature === "chat") {
      statsApi
        .chatPairs(20)
        .then((data) => {
          if (!cancelled) setAnswers(data.pairs);
        })
        .catch(() => {
          /* ignore */
        });
      return () => {
        cancelled = true;
      };
    }

    setLoadingAnswers(true);
    const promise =
      feature === "quiz"
        ? statsApi.quizAnswers({
            onlyIncorrect: filter === "incorrect",
            onlyPartial: filter === "partial",
            limit: 50,
          })
        : feature === "sobes"
          ? statsApi.sobesAnswers({
              onlyIncorrect: filter === "incorrect",
              onlyPartial: filter === "partial",
              limit: 50,
            })
          : feature === "design"
            ? statsApi.designAnswers({
                onlyIncorrect: filter === "incorrect",
                onlyPartial: filter === "partial",
                limit: 50,
              })
            : Promise.resolve({ answers: [] });

    promise
      .then((data) => {
        if (!cancelled) setAnswers((data as { answers: unknown[] }).answers);
      })
      .catch(() => {
        /* ignore */
      })
      .finally(() => {
        if (!cancelled) setLoadingAnswers(false);
      });

    return () => {
      cancelled = true;
    };
  }, [feature, filter]);

  return (
    <div>
      <ModeCard feature={feature} breakdown={breakdown} />

      {feature !== "chat" && (
        <div className={styles.filterBar}>
          <Button variant={filter === "incorrect" ? "primary" : "secondary"} onClick={() => setFilter("incorrect")}>
            Только неправильные
          </Button>
          <Button variant={filter === "partial" ? "primary" : "secondary"} onClick={() => setFilter("partial")}>
            Только частичные
          </Button>
          <Button variant={filter === "all" ? "primary" : "secondary"} onClick={() => setFilter("all")}>
            Все
          </Button>
        </div>
      )}

      {loadingAnswers && <p className={styles.loading}>Загружаем разборы…</p>}

      {!loadingAnswers && answers.length === 0 && (
        <p className={styles.emptyText}>
          {feature === "chat"
            ? "В чате пока нет сообщений. Задайте ассистенту вопрос."
            : "Нет ответов по выбранному фильтру."}
        </p>
      )}

      <div className={styles.answers}>
        {feature === "quiz" &&
          (answers as Array<{
            category: "correct" | "partial" | "incorrect";
            question_text: string;
            user_answer: string;
            correct_answer: string;
            explanation: string;
          }>).map((a, i) => (
            <AnswerCard key={i} category={a.category} title={a.question_text}>
              <p>
                <strong>Ваш ответ:</strong> {a.user_answer}
              </p>
              <p>
                <strong>Правильный ответ:</strong> {a.correct_answer}
              </p>
              {a.explanation && (
                <p>
                  <strong>Разбор:</strong> {a.explanation}
                </p>
              )}
            </AnswerCard>
          ))}

        {feature === "sobes" &&
          (answers as Array<{
            category: "correct" | "partial" | "incorrect";
            question_text: string;
            topic: string;
            user_answer: string;
            reference_answer: string;
            score_percent: number;
            covered_points: string[];
            missed_points: string[];
            techlead_explanation: string;
          }>).map((a, i) => (
            <AnswerCard key={i} category={a.category} title={a.question_text} subtitle={`Тема: ${a.topic} · Оценка: ${a.score_percent}%`}>
              <p>
                <strong>Ваш ответ:</strong> {a.user_answer}
              </p>
              {a.reference_answer && (
                <p>
                  <strong>Эталон:</strong> {a.reference_answer}
                </p>
              )}
              {a.covered_points.length > 0 && (
                <p>
                  <strong>Что раскрыто:</strong>
                  <ul>
                    {a.covered_points.map((p, j) => (
                      <li key={j}>{p}</li>
                    ))}
                  </ul>
                </p>
              )}
              {a.missed_points.length > 0 && (
                <p>
                  <strong>Что пропущено:</strong>
                  <ul>
                    {a.missed_points.map((p, j) => (
                      <li key={j}>{p}</li>
                    ))}
                  </ul>
                </p>
              )}
              {a.techlead_explanation && (
                <p>
                  <strong>Разбор тех-лида:</strong> {a.techlead_explanation}
                </p>
              )}
            </AnswerCard>
          ))}

        {feature === "design" &&
          (answers as Array<{
            category: "correct" | "partial" | "incorrect";
            scenario_id: string;
            step_title: string;
            user_answer: string;
            score_percent: number;
            rubric: Record<string, number>;
            covered_points: string[];
            missed_points: string[];
            techlead_explanation: string;
            hint_used: boolean;
          }>).map((a, i) => (
            <AnswerCard
              key={i}
              category={a.category}
              title={a.step_title || a.scenario_id}
              subtitle={`Оценка: ${a.score_percent}%${a.hint_used ? " · использована подсказка" : ""}`}
            >
              <p>
                <strong>Ваш ответ:</strong> {a.user_answer}
              </p>
              {Object.keys(a.rubric).length > 0 && (
                <p>
                  <strong>Рубрика:</strong>
                  <ul>
                    {Object.entries(a.rubric).map(([k, v]) => (
                      <li key={k}>
                        {k}: {v}
                      </li>
                    ))}
                  </ul>
                </p>
              )}
              {a.covered_points.length > 0 && (
                <p>
                  <strong>Что раскрыто:</strong>
                  <ul>
                    {a.covered_points.map((p, j) => (
                      <li key={j}>{p}</li>
                    ))}
                  </ul>
                </p>
              )}
              {a.missed_points.length > 0 && (
                <p>
                  <strong>Что пропущено:</strong>
                  <ul>
                    {a.missed_points.map((p, j) => (
                      <li key={j}>{p}</li>
                    ))}
                  </ul>
                </p>
              )}
              {a.techlead_explanation && (
                <p>
                  <strong>Разбор тех-лида:</strong> {a.techlead_explanation}
                </p>
              )}
            </AnswerCard>
          ))}

        {feature === "chat" &&
          (answers as Array<{ user_message: string; assistant_answer: string; created_at: string }>).map((p, i) => (
            <AnswerCard key={i} category="correct" title="Диалог" subtitle={new Date(p.created_at).toLocaleString()}>
              <p>
                <strong>Вопрос:</strong> {p.user_message}
              </p>
              <p>
                <strong>Ответ ассистента:</strong> {p.assistant_answer}
              </p>
            </AnswerCard>
          ))}
      </div>
    </div>
  );
};

const AnswerCard: React.FC<{
  category: "correct" | "partial" | "incorrect";
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}> = ({ category, title, subtitle, children }) => {
  return (
    <div className={`${styles.answerCard} ${styles[`answerCard_${category}`]}`}>
      <div className={styles.answerHeader}>
        <span className={`${styles.answerBadge} ${styles[`badge_${category}`]}`}>
          {category === "correct" ? "✓ Правильно" : category === "partial" ? "~ Частично" : "✗ Неправильно"}
        </span>
        <h4 className={styles.answerTitle}>{title}</h4>
        {subtitle && <span className={styles.answerSubtitle}>{subtitle}</span>}
      </div>
      <div className={styles.answerBody}>{children}</div>
    </div>
  );
};

const Metric: React.FC<{ label: string; value: number; kind?: "correct" | "partial" | "incorrect" }> = ({ label, value, kind }) => (
  <div className={`${styles.metric} ${kind ? styles[`metric_${kind}`] : ""}`}>
    <span className={styles.metricValue}>{value}</span>
    <span className={styles.metricLabel}>{label}</span>
  </div>
);

export default StatsView;
