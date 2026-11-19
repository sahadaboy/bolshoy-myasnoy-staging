import { useEffect, useRef, useState } from 'react';
import {
  ArrowLeft,
  Beef,
  Bird,
  Check,
  ChefHat,
  ChevronRight,
  Clock3,
  CookingPot,
  Drumstick,
  Droplet,
  Feather,
  Flame,
  Leaf,
  Microwave,
  RotateCcw,
  Soup,
  Thermometer,
  Utensils,
  type LucideIcon,
} from 'lucide-react';
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { BackLink } from '../components/Retail';
import { meatMethods, meatPriorities, meatProteins, meatTimes } from '../data/meatGuide';
import {
  chooseMeatAnswer,
  compatiblePriorities,
  compatibleProteins,
  MEAT_CATALOG_URL,
  meatGuideStep,
  meatMinutes,
  meatSafety,
  meatSteps,
  recommendMeat,
  type MeatAnswers,
} from '../lib/meatGuide';
import './meat-guide.css';

const methodIcons: Record<string, LucideIcon> = {
  kebab: Flame,
  fry: Utensils,
  roast: Microwave,
  soup: Soup,
  stew: CookingPot,
  mince: Beef,
};
const proteinIcons: Record<string, LucideIcon> = {
  chicken: Drumstick,
  turkey: Bird,
  pork: Beef,
  beef: Beef,
  any: ChefHat,
};
const priorityIcons: Record<string, LucideIcon> = {
  juicy: Droplet,
  lean: Leaf,
  tender: Feather,
  quick: Clock3,
  rich: ChefHat,
  light: Leaf,
  meaty: Beef,
};
const questions = [
  'Что будем готовить?',
  'Какое мясо предпочитаете?',
  'Что для вас важнее?',
  'Сколько времени есть на готовку?',
];

export default function MeatGuidePage() {
  const [answers, setAnswers] = useState<MeatAnswers>({});
  const [moving, setMoving] = useState(false);
  const transition = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const navigate = useNavigate();
  const heading = useRef<HTMLHeadingElement>(null);
  const step = meatGuideStep(params.get('step'), answers);
  const result = step === 4 ? recommendMeat(answers) : null;
  const method = meatMethods.find((item) => item.id === answers.method);
  const protein = meatProteins.find((item) => item.id === answers.protein);
  const choices =
    step === 0
      ? meatMethods.map((item) => ({ ...item, icon: methodIcons[item.id] }))
      : step === 1
        ? compatibleProteins(answers.method).map((item) => ({
            ...item,
            icon: proteinIcons[item.id],
          }))
        : step === 2
          ? compatiblePriorities(answers.method, answers.protein).map((id) => ({
              id,
              label: meatPriorities[id],
              icon: priorityIcons[id],
            }))
          : meatTimes.map((item) => ({ ...item, icon: Clock3 }));

  useEffect(() => {
    setMoving(false);
    return () => {
      if (transition.current !== null) {
        clearTimeout(transition.current);
        transition.current = null;
      }
    };
  }, [location.key]);
  useEffect(() => {
    heading.current?.focus({ preventScroll: true });
  }, [step]);

  function choose(value: string) {
    if (transition.current !== null || step > 3) return;
    const next = chooseMeatAnswer(answers, meatSteps[step], value);
    setAnswers(next);
    setMoving(true);
    transition.current = setTimeout(
      () => {
        transition.current = null;
        setParams({ step: String(step + 1) });
        window.scrollTo({ top: 0, behavior: 'instant' });
      },
      window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 140,
    );
  }
  function back() {
    if (transition.current !== null) {
      clearTimeout(transition.current);
      transition.current = null;
    }
    setMoving(false);
    navigate(-1);
  }
  function restart() {
    setAnswers({});
    setParams({}, { replace: true });
    window.scrollTo({ top: 0, behavior: 'instant' });
  }
  function changeTime() {
    setParams({ step: '3' });
  }

  return (
    <div className="meat-guide">
      {step === 0 ? (
        <BackLink fallback="/ideas" />
      ) : (
        <button className="retail-back" onClick={back}>
          <ArrowLeft size={19} aria-hidden="true" />
          Назад
        </button>
      )}
      <div className="page-intro">
        <h1>Какое мясо выбрать?</h1>
        <p>Подскажем подходящий отруб для вашего блюда</p>
      </div>
      {step < 4 ? (
        <>
          <div className="dinner-progress">
            <span>{step + 1} из 4</span>
            <progress max={4} value={step + 1} aria-label="Прогресс подбора мяса" />
          </div>
          <section className="dinner-step" key={step} aria-labelledby="meat-question">
            <h2 id="meat-question" ref={heading} tabIndex={-1}>
              {questions[step]}
            </h2>
            {step > 0 && (
              <p className="meat-guide-context">
                {method?.label}
                {step > 1 ? ` · ${protein?.label}` : ''}
              </p>
            )}
            <div
              className="meat-guide-choices"
              role="group"
              aria-label={questions[step]}
              aria-busy={moving}
            >
              {choices.map(({ id, label, icon: Icon }) => (
                <button
                  type="button"
                  key={id}
                  aria-pressed={answers[meatSteps[step]] === id}
                  disabled={moving}
                  onClick={() => choose(id)}
                >
                  <Icon size={23} strokeWidth={1.6} aria-hidden="true" />
                  <span>{label}</span>
                  {answers[meatSteps[step]] === id && (
                    <Check className="meat-choice-check" size={15} aria-hidden="true" />
                  )}
                </button>
              ))}
            </div>
            {step === 3 && (
              <button className="retail-text-link" onClick={() => choose('any')} disabled={moving}>
                Пропустить <ChevronRight size={16} aria-hidden="true" />
              </button>
            )}
          </section>
        </>
      ) : (
        <section className="dinner-step meat-guide-result" aria-labelledby="meat-result">
          <p className="meat-guide-context">
            {method?.label} · {answers.priority && meatPriorities[answers.priority]}
          </p>
          {result?.status === 'match' ? (
            <>
              <p className="meat-result-eyebrow">Ваш выбор</p>
              <h2 id="meat-result" ref={heading} tabIndex={-1}>
                {result.primary.cut.name}
              </h2>
              <p>{result.primary.use.description}</p>
              <p className="meat-guide-time">
                <Clock3 size={17} aria-hidden="true" />
                {meatMinutes(result.primary.use.minutes)}
              </p>
              <section className="meat-result-block">
                <h3>Почему подходит</h3>
                <ul>
                  {result.primary.cut.facts.map((fact) => (
                    <li key={fact}>
                      <Check size={17} aria-hidden="true" />
                      <span>{fact}</span>
                    </li>
                  ))}
                </ul>
              </section>
              <section className="meat-result-block">
                <h3>Как приготовить</h3>
                <p>{result.primary.use.advice}</p>
                <p className="meat-time-note">
                  Время ориентировочное, без маринования и размораживания. Размер кусков и нагрев
                  влияют на готовность.
                </p>
                <div className="meat-safety">
                  <Thermometer size={18} aria-hidden="true" />
                  <p>{meatSafety(result.primary.cut.protein, answers.method!)}</p>
                </div>
              </section>
              {result.alternative && (
                <section className="meat-result-block">
                  <h3>Альтернативный вариант</h3>
                  <strong>{result.alternative.cut.name}</strong>
                  <p>{result.alternative.use.description}</p>
                  <small>{meatMinutes(result.alternative.use.minutes)}</small>
                </section>
              )}
            </>
          ) : (
            <div className="meat-result-block">
              <h2 id="meat-result" ref={heading} tabIndex={-1}>
                {result?.status === 'time-conflict'
                  ? 'Этому блюду нужно больше времени'
                  : 'Изменим выбор?'}
              </h2>
              <p>
                {result?.status === 'time-conflict'
                  ? `Для этого сочетания лучше заложить примерно ${result.requiredMinutes} минут. Размер кусков может увеличить это время. Быстрый нагрев не сделает плотное мясо мягким.`
                  : 'Для такого сочетания нет подходящего отруба в нашем помощнике. Попробуйте другой вид мяса или способ приготовления.'}
              </p>
              <button className="button button-secondary" onClick={changeTime}>
                Изменить время
              </button>
            </div>
          )}
          <div className="meat-guide-actions">
            <Link className="button button-primary" to={MEAT_CATALOG_URL}>
              Перейти к ассортименту мяса <ChevronRight size={18} aria-hidden="true" />
            </Link>
            <p>Ассортимент и наличие уточняйте в каталоге и магазине.</p>
            <button className="button button-secondary" onClick={restart}>
              <RotateCcw size={16} aria-hidden="true" />
              Подобрать заново
            </button>
          </div>
        </section>
      )}
    </div>
  );
}
