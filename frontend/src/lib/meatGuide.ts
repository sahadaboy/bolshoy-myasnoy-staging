import {
  meatCuts,
  meatMethods,
  meatProteins,
  meatTimes,
  type MeatCut,
  type MeatMethod,
  type MeatPriority,
  type MeatProtein,
  type MeatTime,
  type MeatUse,
} from '../data/meatGuide';

export const MEAT_CATALOG_URL = '/catalog?category_group=meat';
export interface MeatAnswers {
  method?: MeatMethod;
  protein?: MeatProtein | 'any';
  priority?: MeatPriority;
  time?: MeatTime;
}
export const meatSteps = ['method', 'protein', 'priority', 'time'] as const;

export function compatibleProteins(method: MeatMethod | undefined) {
  return meatProteins.filter(
    ({ id }) =>
      id === 'any' || meatCuts.some((cut) => cut.protein === id && method && cut.uses[method]),
  );
}

export function compatiblePriorities(
  method: MeatMethod | undefined,
  protein: MeatAnswers['protein'],
) {
  return (
    meatMethods
      .find((item) => item.id === method)
      ?.priorities.filter((priority) =>
        meatCuts.some(
          (cut) =>
            (protein === 'any' || cut.protein === protein) &&
            method &&
            cut.uses[method]?.priorities.includes(priority),
        ),
      ) || []
  );
}

/** Revisit keeps answers; changing a parent clears only incompatible descendants. */
export function chooseMeatAnswer(
  answers: MeatAnswers,
  key: (typeof meatSteps)[number],
  value: string,
): MeatAnswers {
  if (key === 'method') {
    const method = meatMethods.find((item) => item.id === value);
    if (!method) return answers;
    if (answers.method === value) return answers;
    return {
      ...answers,
      method: method.id,
      priority: undefined,
      protein: compatibleProteins(method.id).some((item) => item.id === answers.protein)
        ? answers.protein
        : undefined,
    };
  }
  if (key === 'protein' && compatibleProteins(answers.method).some((item) => item.id === value)) {
    const protein = value as MeatAnswers['protein'];
    return {
      ...answers,
      protein,
      priority: compatiblePriorities(answers.method, protein).includes(answers.priority!)
        ? answers.priority
        : undefined,
    };
  }
  if (
    key === 'priority' &&
    compatiblePriorities(answers.method, answers.protein).includes(value as MeatPriority)
  )
    return { ...answers, priority: value as MeatPriority };
  if (key === 'time' && meatTimes.some((item) => item.id === value))
    return { ...answers, time: value as MeatTime };
  return answers;
}

export function meatGuideStep(requested: string | null, answers: MeatAnswers) {
  const requestedStep = Number(requested || 0);
  const firstMissing = meatSteps.findIndex((key) => !answers[key]);
  const lastAllowed = firstMissing === -1 ? 4 : firstMissing;
  return Number.isInteger(requestedStep) && requestedStep >= 0
    ? Math.min(requestedStep, lastAllowed, 4)
    : 0;
}

export interface MeatMatch {
  cut: MeatCut;
  use: MeatUse;
}
export type MeatRecommendation =
  | { status: 'incomplete' }
  | { status: 'time-conflict'; requiredMinutes: number }
  | { status: 'no-match' }
  | { status: 'match'; primary: MeatMatch; alternative?: MeatMatch };

const preferredProtein: Record<MeatMethod, MeatProtein> = {
  kebab: 'pork',
  fry: 'chicken',
  roast: 'chicken',
  soup: 'chicken',
  stew: 'beef',
  mince: 'pork',
};
export function recommendMeat(answers: MeatAnswers): MeatRecommendation {
  const method = meatMethods.find((item) => item.id === answers.method);
  const time = meatTimes.find((item) => item.id === answers.time);
  if (
    !method ||
    !time ||
    !method.priorities.includes(answers.priority!) ||
    !compatibleProteins(method.id).some((item) => item.id === answers.protein)
  )
    return { status: 'incomplete' };
  const priority = answers.priority!;
  const candidates: MeatMatch[] = meatCuts.flatMap((cut) => {
    const use = cut.uses[method.id];
    if (
      !use ||
      (answers.protein !== 'any' && cut.protein !== answers.protein) ||
      !use.priorities.includes(priority)
    )
      return [];
    return [{ cut, use }];
  });
  if (!candidates.length) return { status: 'no-match' };
  // The whole planning range must fit; never shorten a slow cut to fit a budget.
  const fits = candidates.filter(({ use }) => use.minutes[1] <= time.limit);
  if (!fits.length)
    return {
      status: 'time-conflict',
      requiredMinutes: Math.min(...candidates.map(({ use }) => use.minutes[1])),
    };
  const score = ({ cut, use }: MeatMatch) =>
    (use.priorities[0] === priority ? 20 : 0) +
    (cut.protein === preferredProtein[method.id] ? 4 : 0) +
    (priority === 'lean' && cut.fat === 'lean' ? 10 : 0) -
    (priority === 'quick' ? use.minutes[1] / 10 : 0);
  const sorted = [...fits].sort(
    (a, b) => score(b) - score(a) || a.cut.id.localeCompare(b.cut.id, 'en'),
  );
  return { status: 'match', primary: sorted[0], alternative: sorted[1] };
}

export function meatSafety(protein: MeatProtein, method: MeatMethod) {
  if (protein === 'chicken' || protein === 'turkey')
    return 'Птицу, в том числе фарш, доведите минимум до 74 °C в самой толстой части. Термометр не должен касаться кости.';
  if (method === 'mince')
    return 'Говяжий или свиной фарш доведите минимум до 71 °C в центре котлеты. Цвет внутри не заменяет проверку термометром.';
  return 'Цельный отруб говядины или свинины доведите минимум до 63 °C и дайте отдохнуть 3 минуты. При тушении для мягкости потребуется более долгий нагрев.';
}

export function meatMinutes([min, max]: readonly [number, number]) {
  const value = (minutes: number) => (minutes % 60 === 0 ? `${minutes / 60} ч` : `${minutes} мин`);
  return min === max ? value(min) : `${value(min)} – ${value(max)}`;
}
