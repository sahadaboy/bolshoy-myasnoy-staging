import { CookingPot, ChevronRight } from 'lucide-react';
import { Link } from 'react-router-dom';

export function DinnerInvite() {
  return (
    <Link className="retail-dinner-invite" to="/ideas/dinner">
      <CookingPot size={30} strokeWidth={1.5} />
      <span>
        <strong>Собрать идею для ужина</strong>
        <small>Из того, что есть дома, и продуктов нашего магазина</small>
      </span>
      <ChevronRight size={20} />
    </Link>
  );
}
