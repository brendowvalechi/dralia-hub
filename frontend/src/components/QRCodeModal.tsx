import { useEffect, useState } from 'react'
import { X, RefreshCw, Wifi } from 'lucide-react'
import { getQRCode, syncInstance } from '../api'
import { useToast } from '../contexts/ToastContext'
import { useQueryClient } from '@tanstack/react-query'

interface Props {
  instanceId: string
  instanceName: string
  onClose: () => void
}

export default function QRCodeModal({ instanceId, instanceName, onClose }: Props) {
  const { toast } = useToast()
  const qc = useQueryClient()
  const [qr, setQr] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)

  const fetchQR = async () => {
    setLoading(true)
    try {
      const { data } = await getQRCode(instanceId)
      setQr(data.qrcode ?? null)
      if (data.status === 'connected') {
        toast('Instância já conectada!', 'success')
        qc.invalidateQueries({ queryKey: ['instances'] })
        onClose()
      }
    } catch {
      toast('Erro ao buscar QR Code. Verifique se a Evolution API está rodando.', 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleSync = async () => {
    setSyncing(true)
    try {
      await syncInstance(instanceId)
      qc.invalidateQueries({ queryKey: ['instances'] })
      toast('Status sincronizado', 'success')
      onClose()
    } catch {
      toast('Erro ao sincronizar', 'error')
    } finally {
      setSyncing(false)
    }
  }

  useEffect(() => {
    fetchQR()
    const interval = setInterval(fetchQR, 30_000)
    return () => clearInterval(interval)
  }, [instanceId])

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative bg-white rounded-2xl shadow-xl p-6 w-full max-w-sm mx-4">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="font-semibold text-gray-800">Conectar WhatsApp</h2>
            <p className="text-xs text-gray-400 font-mono">{instanceName}</p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X size={18} />
          </button>
        </div>

        {loading ? (
          <div className="flex items-center justify-center h-64">
            <div className="w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : qr ? (
          <>
            <p className="text-sm text-gray-500 mb-3 text-center">
              Abra o WhatsApp → Aparelhos conectados → Conectar aparelho
            </p>
            <div className="flex justify-center">
              <img
                src={qr.startsWith('data:') ? qr : `data:image/png;base64,${qr}`}
                alt="QR Code WhatsApp"
                className="w-56 h-56 rounded-lg border border-gray-200"
              />
            </div>
            <p className="text-xs text-gray-400 text-center mt-2">QR code atualiza automaticamente a cada 30s</p>
          </>
        ) : (
          <div className="flex flex-col items-center justify-center h-40 gap-2">
            <p className="text-gray-400 text-sm">QR Code não disponível</p>
            <p className="text-xs text-gray-300">Verifique se a Evolution API está rodando</p>
          </div>
        )}

        <div className="flex gap-2 mt-4">
          <button
            onClick={fetchQR}
            disabled={loading}
            className="flex-1 flex items-center justify-center gap-1.5 py-2 text-sm border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-50"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} /> Atualizar QR
          </button>
          <button
            onClick={handleSync}
            disabled={syncing}
            className="flex-1 flex items-center justify-center gap-1.5 py-2 text-sm bg-green-600 text-white rounded-lg hover:bg-green-500 disabled:opacity-50"
          >
            <Wifi size={14} /> Já escaneei
          </button>
        </div>
      </div>
    </div>
  )
}
