import { Beef, ChevronRight } from 'lucide-react';
import { Link } from 'react-router-dom';

export function MeatGuideInvite() {
  return (
    <Link className="retail-dinner-invite" to="/ideas/meat">
      <Beef size={30} strokeWidth={1.5} aria-hidden="true" />
      <span>
        <strong>Какое мясо выбрать?</strong>
        <small>Подскажем подходящий отруб для вашего блюда</small>
      </span>
      <ChevronRight size={20} aria-hidden="true" />
    </Link>
  );
}
