import Image from "next/image";
import symbol from "./assets/ukladen-avatar.png";
import styles from "./brand.module.css";

export function Brand() {
  return <span className={styles.brand}>
    <Image className={styles.symbol} src={symbol} alt="" width={48} height={48} sizes="48px" />
    <span>Ukladen</span>
  </span>;
}
