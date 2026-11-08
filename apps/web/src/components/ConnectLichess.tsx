import { useConnectLichess } from '../hooks/useLinks';
import { currentLinkReturnPath } from '../lib/linkReturnTo';
import { PillButton } from './ui/PillButton';

export function ConnectLichessButton({
  size = 'md',
  fullWidth = false,
}: {
  size?: 'sm' | 'md' | 'lg';
  fullWidth?: boolean;
}) {
  const connect = useConnectLichess();
  return (
    <div className={fullWidth ? 'flex w-full flex-col gap-1' : 'flex flex-col gap-1'}>
      <PillButton
        variant="primary"
        size={size}
        fullWidth={fullWidth}
        disabled={connect.isPending}
        onClick={() => connect.mutate(currentLinkReturnPath())}
      >
        {connect.isPending ? 'Opening Lichess…' : 'Connect Lichess'}
      </PillButton>
      {connect.error && <p className="text-xs text-red">{connect.error.message}</p>}
    </div>
  );
}

export function NotAffiliated() {
  return <p className="text-micro text-text-tertiary">Not affiliated with Lichess.</p>;
}
