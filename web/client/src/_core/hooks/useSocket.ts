import { useSocketContext } from '../../contexts/SocketContext';

export function useSocket(_userId?: string | undefined) {
    const { isConnected, lastMessage, sendMessage } = useSocketContext();
    return { isConnected, lastMessage, sendMessage };
}
